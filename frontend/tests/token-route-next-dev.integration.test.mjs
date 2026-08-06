import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import test from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const frontendDirectory = fileURLToPath(new URL('../', import.meta.url));
const nextCli = fileURLToPath(new URL('../node_modules/next/dist/bin/next', import.meta.url));

async function reserveLoopbackPort() {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');

  const address = server.address();
  assert.ok(address && typeof address !== 'string');

  await new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
  return address.port;
}

async function waitForNext(baseUrl, child) {
  const deadline = Date.now() + 45_000;

  while (Date.now() < deadline) {
    if (child !== undefined && child.exitCode !== null) {
      throw new Error('Next development server exited before becoming ready.');
    }

    try {
      const response = await fetch(baseUrl, { signal: AbortSignal.timeout(1_000) });
      await response.body?.cancel();
      return;
    } catch {
      await delay(100);
    }
  }

  throw new Error('Next development server did not become ready.');
}

async function stopChild(child) {
  if (child.exitCode !== null) {
    return;
  }

  child.kill('SIGTERM');
  for (let attempt = 0; attempt < 50 && child.exitCode === null; attempt += 1) {
    await delay(100);
  }

  if (child.exitCode === null) {
    child.kill('SIGKILL');
  }
}

async function postToken(baseUrl, headers = {}) {
  return fetch(`${baseUrl}/api/token`, {
    body: '{}',
    headers: { 'content-type': 'application/json', ...headers },
    method: 'POST',
  });
}

test(
  'real Next development requests accept direct loopback and reject forged public forwarding',
  { timeout: 60_000 },
  async () => {
    const suppliedBaseUrl = process.env.FINED_NEXT_DEV_TEST_URL;
    let child;
    let baseUrl;

    if (suppliedBaseUrl !== undefined) {
      const parsed = new URL(suppliedBaseUrl);
      assert.equal(parsed.protocol, 'http:');
      assert.ok(parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost');
      baseUrl = parsed.origin;
    } else {
      const port = await reserveLoopbackPort();
      baseUrl = `http://127.0.0.1:${port}`;
      child = spawn(
        process.execPath,
        [nextCli, 'dev', '--turbopack', '--hostname', '127.0.0.1', '--port', String(port)],
        {
          cwd: frontendDirectory,
          env: {
            AGENT_NAME: 'my-agent',
            LIVEKIT_API_KEY: 'integration-key',
            LIVEKIT_API_SECRET: 'integration-secret-that-is-long-enough-for-local-signing',
            LIVEKIT_URL: 'wss://integration.invalid',
            NEXT_TELEMETRY_DISABLED: '1',
            NODE_ENV: 'development',
            PATH: process.env.PATH ?? '',
            UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT: 'false',
          },
          stdio: 'ignore',
        }
      );
    }

    try {
      await waitForNext(baseUrl, child);

      const directResponse = await postToken(baseUrl);
      assert.equal(directResponse.status, 200);
      await directResponse.body?.cancel();

      for (const headers of [
        { 'x-forwarded-for': '203.0.113.8' },
        { 'x-forwarded-host': 'public.example' },
      ]) {
        const forgedResponse = await postToken(baseUrl, headers);
        assert.equal(forgedResponse.status, 403);
        assert.deepEqual(await forgedResponse.json(), {
          error: 'Unable to issue connection details.',
        });
      }
    } finally {
      if (child !== undefined) {
        await stopChild(child);
      }
    }
  }
);
