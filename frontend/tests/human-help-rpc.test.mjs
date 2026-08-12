import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8');
  module._compile(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      fileName: filename,
    }).outputText,
    filename
  );
};

const { createHumanHelpRpcHandler, decodeHumanHelpRequest } = require('../lib/human-help.ts');

function request(overrides = {}) {
  return {
    version: 1,
    reference_id: 'HELP-A1B2-C3D4-E5F6-0123-4567-89AB',
    reason: 'suspected_fraud',
    summary: 'The learner reports an unrecognised account transaction.',
    checks_completed: 'FinEd confirmed that the activity was not recognised.',
    urgency: 'high',
    language: 'english',
    follow_up_method: 'in_app',
    status: 'open',
    created_at: '2026-08-12T06:30:00+00:00',
    ...overrides,
  };
}

test('strict decoder accepts one bounded public human-help request', () => {
  assert.deepEqual(decodeHumanHelpRequest(JSON.stringify(request())), request());
});

test('decoder rejects extra fields, private values and invalid categories', () => {
  for (const candidate of [
    request({ caller_id: 'learner-1' }),
    request({ summary: 'OTP is 123456' }),
    request({ summary: 'PAN ABCDE1234F was shared' }),
    request({ summary: 'Account 1234 5678 9012 was shared' }),
    request({ reason: 'normal_question' }),
    request({ follow_up_method: 'email' }),
    request({ status: 'resolved' }),
  ]) {
    assert.throws(() => decodeHumanHelpRequest(JSON.stringify(candidate)));
  }
});

test('RPC handler accepts only the connected agent and returns a narrow acknowledgement', async () => {
  const shown = [];
  const handler = createHumanHelpRpcHandler('agent-1', (value) => shown.push(value));
  const payload = JSON.stringify(request());

  assert.equal(
    await handler({ callerIdentity: 'agent-1', payload }),
    '{"version":1,"opened":true}'
  );
  assert.deepEqual(shown, [request()]);
  await assert.rejects(() => handler({ callerIdentity: 'other-agent', payload }), /authorized/);
  assert.deepEqual(shown, [request()]);
});
