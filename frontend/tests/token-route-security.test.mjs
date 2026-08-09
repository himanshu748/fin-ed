import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isIP } from 'node:net';
import test from 'node:test';
import ts from 'typescript';

const routeSource = readFileSync(new URL('../app/api/token/route.ts', import.meta.url), 'utf8');
const packageJson = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const compiledRoute = ts.transpileModule(routeSource, {
  compilerOptions: {
    esModuleInterop: true,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
  fileName: 'route.ts',
}).outputText;

const REQUIRED_ENV = {
  AGENT_NAME: 'my-agent',
  LIVEKIT_API_KEY: 'test-key',
  LIVEKIT_API_SECRET: 'test-secret',
  LIVEKIT_URL: 'wss://voice.invalid',
  NODE_ENV: 'development',
};

const TEST_UUIDS = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'];

function loadRoute({ env = REQUIRED_ENV, tokenError, uuidValues = TEST_UUIDS } = {}) {
  const accessTokens = [];
  const errorLogs = [];
  const roomConfigCalls = [];
  const remainingUuids = [...uuidValues];

  class AccessToken {
    constructor(apiKey, apiSecret, options) {
      this.apiKey = apiKey;
      this.apiSecret = apiSecret;
      this.options = options;
      accessTokens.push(this);
    }

    addGrant(grant) {
      this.grant = grant;
    }

    async toJwt() {
      if (tokenError !== undefined) {
        throw tokenError;
      }
      return 'test-token';
    }
  }

  const requireMock = (specifier) => {
    if (specifier === 'node:crypto') {
      return {
        randomUUID() {
          const value = remainingUuids.shift();
          assert.ok(value, 'the route must request only the expected UUIDs');
          return value;
        },
      };
    }
    if (specifier === 'node:net') {
      return { isIP };
    }
    if (specifier === 'next/server') {
      return {
        NextResponse: {
          json(body, init) {
            return Response.json(body, init);
          },
        },
      };
    }
    if (specifier === 'livekit-server-sdk') {
      return { AccessToken };
    }
    if (specifier === '@livekit/protocol') {
      return {
        RoomConfiguration: {
          fromJson(value, options) {
            roomConfigCalls.push({ options, value });
            return { options, value };
          },
        },
      };
    }
    if (specifier === '@/lib/learning-modes') {
      return {
        sanitizeParticipantMetadataRequest(body) {
          return typeof body?.participant_metadata === 'string'
            ? body.participant_metadata
            : '{"learning_mode":"general"}';
        },
      };
    }
    throw new Error(`Unexpected module: ${specifier}`);
  };

  const routeExports = {};
  const evaluate = new Function('require', 'exports', 'process', 'console', compiledRoute);
  evaluate(
    requireMock,
    routeExports,
    { env: { ...env } },
    {
      error(...args) {
        errorLogs.push(args.join(' '));
      },
    }
  );

  return {
    POST: routeExports.POST,
    accessTokens,
    errorLogs,
    remainingUuids,
    roomConfigCalls,
  };
}

function tokenRequest(url, body = {}, headers = {}) {
  const requestUrl = new URL(url);
  const forwardedPort = requestUrl.port || (requestUrl.protocol === 'https:' ? '443' : '80');
  return new Request(url, {
    body: JSON.stringify(body),
    headers: {
      'content-type': 'application/json',
      host: requestUrl.host,
      'x-forwarded-for': '127.0.0.1',
      'x-forwarded-host': requestUrl.host,
      'x-forwarded-port': forwardedPort,
      'x-forwarded-proto': requestUrl.protocol.slice(0, -1),
      ...headers,
    },
    method: 'POST',
  });
}

test('the development server binds to the loopback interface', () => {
  assert.equal(packageJson.scripts.dev, 'next dev --turbopack --hostname 127.0.0.1');
});

test('dispatch configuration is server-owned and caller room_config is ignored', async () => {
  const harness = loadRoute();
  const response = await harness.POST(
    tokenRequest('http://localhost:3000/api/token', {
      participant_metadata: '{"learning_mode":"stocks"}',
      room_config: { agents: [{ agentName: 'attacker-agent' }] },
    })
  );

  assert.equal(response.status, 200);
  assert.equal(harness.roomConfigCalls.length, 1);
  assert.deepEqual(harness.roomConfigCalls[0], {
    options: { ignoreUnknownFields: true },
    value: { agents: [{ agentName: 'my-agent' }] },
  });
  assert.equal(JSON.stringify(harness.roomConfigCalls[0]).includes('attacker-agent'), false);
  assert.deepEqual(harness.accessTokens[0].roomConfig, harness.roomConfigCalls[0]);
});

test('public hosts are blocked by default before a token is created', async () => {
  const harness = loadRoute();
  const response = await harness.POST(tokenRequest('https://fined.example/api/token'));

  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { error: 'Unable to issue connection details.' });
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(harness.accessTokens.length, 0);
  assert.equal(harness.roomConfigCalls.length, 0);
  assert.deepEqual(harness.errorLogs, ['Token request failed.']);
});

test('production rejects even a localhost request without the unsafe opt-in', async () => {
  const harness = loadRoute({
    env: { ...REQUIRED_ENV, NODE_ENV: 'production' },
  });
  const response = await harness.POST(tokenRequest('http://localhost:3000/api/token'));

  assert.equal(response.status, 403);
  assert.equal(harness.accessTokens.length, 0);
  assert.deepEqual(harness.errorLogs, ['Token request failed.']);
});

test('direct development rejects standard Forwarded and unknown X-Forwarded names', async () => {
  for (const [name, value] of [
    ['forwarded', 'for=203.0.113.8;host=localhost:3000'],
    ['x-forwarded-client-cert', 'forged-cert'],
  ]) {
    const harness = loadRoute();
    const response = await harness.POST(
      tokenRequest('http://localhost:3000/api/token', {}, { [name]: value })
    );

    assert.equal(response.status, 403, `${name} must be rejected`);
    assert.equal(harness.accessTokens.length, 0, `${name} must not mint a token`);
  }
});

test('direct development rejects public, conflicting, and malformed synthesized values', async () => {
  for (const [name, value] of [
    ['x-forwarded-for', '203.0.113.8'],
    ['x-forwarded-for', '127.0.0.1, 203.0.113.8'],
    ['x-forwarded-for', 'not-an-ip'],
    ['x-forwarded-host', 'public.example:3000'],
    ['x-forwarded-port', '3001'],
    ['x-forwarded-port', 'not-a-port'],
    ['x-forwarded-proto', 'https'],
    ['x-forwarded-proto', 'http,https'],
  ]) {
    const harness = loadRoute();
    const response = await harness.POST(
      tokenRequest('http://localhost:3000/api/token', {}, { [name]: value })
    );

    assert.equal(response.status, 403, `${name}=${value} must be rejected`);
    assert.equal(harness.accessTokens.length, 0, `${name}=${value} must not mint a token`);
  }
});

test('a coherent loopback-only forwarded chain is accepted in direct development', async () => {
  const harness = loadRoute();
  const response = await harness.POST(
    tokenRequest(
      'http://localhost:3000/api/token',
      {},
      { 'x-forwarded-for': '127.0.0.1, ::1, ::ffff:127.0.0.1' }
    )
  );

  assert.equal(response.status, 200);
  assert.equal(harness.accessTokens.length, 1);
});

test('a forged loopback Host cannot make a public request look local', async () => {
  const harness = loadRoute();
  const response = await harness.POST(
    tokenRequest('https://public.example/api/token', {}, { host: 'localhost:3000' })
  );

  assert.equal(response.status, 403);
  assert.equal(harness.accessTokens.length, 0);
});

test('a Next placeholder URL hostname is allowed when direct request headers are coherent', async () => {
  const harness = loadRoute();
  const response = await harness.POST(
    tokenRequest(
      'http://next-internal.invalid/api/token',
      {},
      {
        host: '127.0.0.1:3000',
        'x-forwarded-host': '127.0.0.1:3000',
        'x-forwarded-port': '3000',
      }
    )
  );

  assert.equal(response.status, 200);
  assert.equal(harness.accessTokens.length, 1);
});

test('localhost passes and uses collision-resistant participant and room identifiers', async () => {
  const harness = loadRoute();
  const response = await harness.POST(tokenRequest('http://127.0.0.1:3000/api/token'));
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(body.roomName, `voice_assistant_room_${TEST_UUIDS[1]}`);
  assert.equal(harness.accessTokens[0].options.identity, `voice_assistant_user_${TEST_UUIDS[0]}`);
  assert.equal(harness.accessTokens[0].options.metadata, '{"learning_mode":"general"}');
  assert.equal(
    response.headers.get('set-cookie'),
    `fined_learner_id=${TEST_UUIDS[0]}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`
  );
  assert.equal(harness.remainingUuids.length, 0);
  assert.deepEqual(harness.errorLogs, []);
});

test('a server-issued learner cookie keeps caller identity stable across calls', async () => {
  // Catches a fresh participant identity wiping Day 4 memory on every connection.
  const harness = loadRoute({ uuidValues: [TEST_UUIDS[1]] });
  const response = await harness.POST(
    tokenRequest(
      'http://127.0.0.1:3000/api/token',
      {},
      { cookie: `theme=light; fined_learner_id=${TEST_UUIDS[0]}` }
    )
  );

  assert.equal(response.status, 200);
  assert.equal(harness.accessTokens[0].options.identity, `voice_assistant_user_${TEST_UUIDS[0]}`);
  assert.equal(response.headers.get('set-cookie'), null);
  assert.equal(harness.remainingUuids.length, 0);
});

test('a malformed learner cookie is replaced instead of becoming an identity', async () => {
  // Catches caller-controlled or delimiter-bearing identities entering LiveKit tokens.
  const harness = loadRoute();
  const response = await harness.POST(
    tokenRequest(
      'http://127.0.0.1:3000/api/token',
      {},
      { cookie: 'fined_learner_id=../../another-user' }
    )
  );

  assert.equal(response.status, 200);
  assert.equal(harness.accessTokens[0].options.identity, `voice_assistant_user_${TEST_UUIDS[0]}`);
  assert.equal(
    response.headers.get('set-cookie'),
    `fined_learner_id=${TEST_UUIDS[0]}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`
  );
});

test('only the exact unsafe demo opt-in permits a proxied public production request', async () => {
  const harness = loadRoute({
    env: {
      ...REQUIRED_ENV,
      NODE_ENV: 'production',
      UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT: 'true',
    },
  });
  const response = await harness.POST(
    tokenRequest(
      'https://demo.example/api/token',
      {},
      { forwarded: 'for=203.0.113.8;host=demo.example' }
    )
  );

  assert.equal(response.status, 200);
  assert.equal(harness.accessTokens.length, 1);

  const inexactHarness = loadRoute({
    env: {
      ...REQUIRED_ENV,
      NODE_ENV: 'production',
      UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT: 'TRUE',
    },
  });
  const inexactResponse = await inexactHarness.POST(
    tokenRequest('http://localhost:3000/api/token')
  );

  assert.equal(inexactResponse.status, 403);
  assert.equal(inexactHarness.accessTokens.length, 0);
});

test('internal failures return and log only fixed sanitized errors', async () => {
  const sensitiveDetail = 'provider request abc-secret failed';
  const harness = loadRoute({ tokenError: new Error(sensitiveDetail) });
  const response = await harness.POST(tokenRequest('http://localhost:3000/api/token'));
  const responseText = await response.text();

  assert.equal(response.status, 500);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(responseText, '{"error":"Unable to issue connection details."}');
  assert.deepEqual(harness.errorLogs, ['Token request failed.']);
  assert.equal(responseText.includes(sensitiveDetail), false);
  assert.equal(harness.errorLogs.join(' ').includes(sensitiveDetail), false);
});
