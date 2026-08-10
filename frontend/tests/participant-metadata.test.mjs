import { TokenSource } from 'livekit-client';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import * as learningModeContract from '../lib/learning-modes.ts';

const {
  LEARNING_MODES,
  participantMetadataRequest,
  sanitizeParticipantMetadata,
  sanitizeParticipantMetadataRequest,
} = learningModeContract;

const GENERAL_METADATA = '{"learning_mode":"general"}';

function assertAppSessionWiring(appSource) {
  const sourceFile = ts.createSourceFile(
    'app.tsx',
    appSource,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX
  );
  const appDeclaration = sourceFile.statements.find(
    (statement) => ts.isFunctionDeclaration(statement) && statement.name?.text === 'App'
  );
  assert.ok(appDeclaration?.body, 'App function declaration must exist');

  const declarations = new Map();
  function visit(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
      declarations.set(node.name.text, node);
    }
    ts.forEachChild(node, visit);
  }
  visit(appDeclaration.body);

  const participantMetadata = declarations.get('participantMetadata');
  assert.ok(participantMetadata, 'App must derive one canonical participantMetadata value');
  assert.ok(
    ts.isCallExpression(participantMetadata.initializer) &&
      participantMetadata.initializer.expression.getText(sourceFile) === 'useMemo',
    'participantMetadata must be stable through useMemo'
  );
  const participantMetadataFactory = participantMetadata.initializer.arguments[0];
  assert.ok(ts.isArrowFunction(participantMetadataFactory));
  assert.ok(ts.isCallExpression(participantMetadataFactory.body));
  assert.equal(
    participantMetadataFactory.body.expression.getText(sourceFile),
    'participantMetadataForLearningMode'
  );
  assert.deepEqual(
    participantMetadataFactory.body.arguments.map((argument) => argument.getText(sourceFile)),
    ['learningMode'],
    'participantMetadata factory must receive learningMode'
  );
  const participantMetadataDependencies = participantMetadata.initializer.arguments[1];
  assert.ok(ts.isArrayLiteralExpression(participantMetadataDependencies));
  assert.deepEqual(
    participantMetadataDependencies.elements.map((element) => element.getText(sourceFile)),
    ['learningMode']
  );

  const tokenSource = declarations.get('tokenSource');
  assert.ok(tokenSource, 'App must declare tokenSource');
  assert.ok(ts.isCallExpression(tokenSource.initializer), 'tokenSource must use a factory hook');
  const tokenSourceFactory = tokenSource.initializer.arguments[0];
  assert.ok(ts.isArrowFunction(tokenSourceFactory), 'tokenSource must use an inline memo factory');
  assert.ok(
    ts.isCallExpression(tokenSourceFactory.body),
    'tokenSource memo must call the mode-scoped factory'
  );
  assert.equal(
    tokenSourceFactory.body.expression.getText(sourceFile),
    'createModeScopedTokenSource'
  );
  assert.deepEqual(
    tokenSourceFactory.body.arguments.map((argument) => argument.getText(sourceFile)),
    ['appConfig', 'participantMetadata']
  );
  const dependencies = tokenSource.initializer.arguments[1];
  assert.ok(
    ts.isArrayLiteralExpression(dependencies),
    'tokenSource must have explicit dependencies'
  );
  assert.deepEqual(
    dependencies.elements.map((element) => element.getText(sourceFile)),
    ['appConfig', 'participantMetadata']
  );

  const fetchOptions = declarations.get('fetchOptions');
  assert.ok(fetchOptions && ts.isCallExpression(fetchOptions.initializer));
  assert.equal(fetchOptions.initializer.expression.getText(sourceFile), 'useMemo');
  const fetchOptionsFactory = fetchOptions.initializer.arguments[0];
  assert.ok(ts.isArrowFunction(fetchOptionsFactory));
  assert.ok(ts.isParenthesizedExpression(fetchOptionsFactory.body));
  assert.ok(ts.isObjectLiteralExpression(fetchOptionsFactory.body.expression));
  assert.ok(
    fetchOptionsFactory.body.expression.properties.some(
      (property) =>
        ts.isShorthandPropertyAssignment(property) && property.name.text === 'participantMetadata'
    ),
    'fetchOptions must carry the canonical participantMetadata value'
  );
  const fetchOptionsDependencies = fetchOptions.initializer.arguments[1];
  assert.ok(ts.isArrayLiteralExpression(fetchOptionsDependencies));
  assert.deepEqual(
    fetchOptionsDependencies.elements.map((element) => element.getText(sourceFile)),
    ['appConfig.agentName', 'participantMetadata', 'room'],
    'fetchOptions dependencies must track metadata and the persistent room'
  );

  const session = declarations.get('session');
  assert.ok(session && ts.isCallExpression(session.initializer));
  assert.equal(session.initializer.expression.getText(sourceFile), 'useSession');
  assert.deepEqual(
    session.initializer.arguments.map((argument) => argument.getText(sourceFile)),
    ['tokenSource', 'fetchOptions']
  );
}

test('all eight learning modes survive sanitation', () => {
  assert.equal(LEARNING_MODES.length, 8);

  for (const { value } of LEARNING_MODES) {
    assert.equal(
      sanitizeParticipantMetadata(JSON.stringify({ learning_mode: value })),
      JSON.stringify({ learning_mode: value })
    );
  }
});

test('invalid metadata falls back to compact general metadata', () => {
  const invalidValues = [
    undefined,
    null,
    42,
    '{',
    'null',
    '[]',
    '"stocks"',
    '{}',
    '{"learning_mode":"unknown"}',
    '{"learning_mode":"stocks","extra":true}',
  ];

  for (const value of invalidValues) {
    assert.equal(sanitizeParticipantMetadata(value), GENERAL_METADATA);
  }
});

test('the UTF-8 byte limit allows 1024 bytes and rejects 1025 bytes', () => {
  const compact = '{"learning_mode":"stocks"}';
  const exactly1024Bytes = compact + ' '.repeat(1024 - compact.length);
  const exactly1025Bytes = `${exactly1024Bytes} `;

  assert.equal(new TextEncoder().encode(exactly1024Bytes).byteLength, 1024);
  assert.equal(new TextEncoder().encode(exactly1025Bytes).byteLength, 1025);
  assert.equal(sanitizeParticipantMetadata(exactly1024Bytes), '{"learning_mode":"stocks"}');
  assert.equal(sanitizeParticipantMetadata(exactly1025Bytes), GENERAL_METADATA);
});

test('the byte limit measures multibyte input instead of JavaScript string length', () => {
  const multibyteInput = `{"learning_mode":"${'अ'.repeat(400)}","learning_mode":"stocks"}`;

  assert.ok(multibyteInput.length < 1024);
  assert.ok(new TextEncoder().encode(multibyteInput).byteLength > 1024);
  assert.equal(sanitizeParticipantMetadata(multibyteInput), GENERAL_METADATA);
});

test('sanitized output always has exactly one learning_mode key', () => {
  for (const value of [
    '{"learning_mode":"etfs"}',
    '{"learning_mode":"stocks","other":"value"}',
    'not json',
  ]) {
    const output = JSON.parse(sanitizeParticipantMetadata(value));
    assert.deepEqual(Object.keys(output), ['learning_mode']);
  }
});

test('sandbox metadata maps from camelCase value to the sole snake_case request key', () => {
  const metadata = '{"learning_mode":"bonds"}';

  assert.deepEqual(participantMetadataRequest(metadata), {
    participant_metadata: metadata,
  });
  assert.deepEqual(Object.keys(participantMetadataRequest(undefined)), ['participant_metadata']);
});

test('the token route reads only participant_metadata and sanitizes it', () => {
  assert.equal(
    sanitizeParticipantMetadataRequest({
      participant_metadata: '{"learning_mode":"ipos"}',
      participant_identity: 'ignored',
      participant_name: 'ignored',
      room_name: 'ignored',
      metadata: { arbitrary: true },
    }),
    '{"learning_mode":"ipos"}'
  );
  assert.equal(
    sanitizeParticipantMetadataRequest({ metadata: '{"learning_mode":"stocks"}' }),
    GENERAL_METADATA
  );
});

test('an installed configurable TokenSource can reuse its first valid token after metadata changes', async () => {
  const fetchedMetadata = [];
  const validTestToken = 'eyJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZXN0In0.';
  const source = TokenSource.custom(async (options) => {
    fetchedMetadata.push(options.participantMetadata);
    return {
      serverUrl: 'wss://voice.invalid',
      participantToken: validTestToken,
    };
  });

  const general = await source.fetch({ participantMetadata: GENERAL_METADATA });
  const stocks = await source.fetch({ participantMetadata: '{"learning_mode":"stocks"}' });

  assert.deepEqual(fetchedMetadata, [GENERAL_METADATA]);
  assert.equal(stocks.participantToken, general.participantToken);
});

test('canonical participant metadata changes the token-source memo key', () => {
  assert.equal(typeof learningModeContract.participantMetadataForLearningMode, 'function');

  const general = learningModeContract.participantMetadataForLearningMode('general');
  const stocks = learningModeContract.participantMetadataForLearningMode('stocks');

  assert.equal(general, '{"learning_mode":"general"}');
  assert.equal(stocks, '{"learning_mode":"stocks"}');
  assert.notEqual(general, stocks);
});

test('App scopes the configurable token source to canonical participant metadata', () => {
  const appSource = readFileSync(new URL('../components/app/app.tsx', import.meta.url), 'utf8');
  assertAppSessionWiring(appSource);

  const generalPinnedSource = appSource.replace(
    '() => participantMetadataForLearningMode(learningMode),\n    [learningMode]',
    "() => participantMetadataForLearningMode('general'),\n    []"
  );
  assert.notEqual(generalPinnedSource, appSource, 'in-memory stale wiring mutation must apply');
  assert.throws(
    () => assertAppSessionWiring(generalPinnedSource),
    /participantMetadata factory must receive learningMode/
  );

  const staleFetchOptionsSource = appSource.replace(
    '    [appConfig.agentName, participantMetadata, room]\n  );\n\n  const session',
    '    [appConfig.agentName, room]\n  );\n\n  const session'
  );
  assert.notEqual(
    staleFetchOptionsSource,
    appSource,
    'in-memory stale fetchOptions mutation must apply'
  );
  assert.throws(
    () => assertAppSessionWiring(staleFetchOptionsSource),
    /fetchOptions dependencies must track metadata and the persistent room/
  );
});

test('sandbox response handling rejects HTTP and malformed bodies with one fixed error', async () => {
  assert.equal(typeof learningModeContract.readSandboxConnectionResponse, 'function');
  const expectedMessage = 'Unable to fetch connection details.';
  let parsedFailureBody = false;

  await assert.rejects(
    learningModeContract.readSandboxConnectionResponse({
      ok: false,
      json: async () => {
        parsedFailureBody = true;
        return { detail: 'sensitive response body' };
      },
    }),
    { message: expectedMessage }
  );
  assert.equal(parsedFailureBody, false);

  await assert.rejects(
    learningModeContract.readSandboxConnectionResponse({
      ok: true,
      json: async () => {
        throw new Error('sensitive parser detail');
      },
    }),
    { message: expectedMessage }
  );

  await assert.rejects(
    learningModeContract.readSandboxConnectionResponse({
      ok: true,
      json: async () => ({ serverUrl: '', participantToken: '' }),
    }),
    { message: expectedMessage }
  );

  for (const responseBody of [
    { serverUrl: '   ', participantToken: 'test-token' },
    { serverUrl: 'wss://voice.invalid', participantToken: '\t\n' },
  ]) {
    await assert.rejects(
      learningModeContract.readSandboxConnectionResponse({
        ok: true,
        json: async () => responseBody,
      }),
      { message: expectedMessage }
    );
  }
});

test('sandbox response handling returns a valid connection response unchanged', async () => {
  const responseBody = {
    serverUrl: 'wss://voice.invalid',
    participantToken: 'test-token',
  };

  assert.deepEqual(
    await learningModeContract.readSandboxConnectionResponse({
      ok: true,
      json: async () => responseBody,
    }),
    responseBody
  );
});
