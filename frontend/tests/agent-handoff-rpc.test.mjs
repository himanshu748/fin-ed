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

const {
  AGENT_STATUS_RPC_METHOD,
  AGENT_STATUS_QUERY_RPC_METHOD,
  MAX_AGENT_STATUS_RPC_BYTES,
  FINED_ACTIVE_AGENT_STATUS,
  TAXED_ACTIVE_AGENT_STATUS,
  createAgentStatusRpcHandler,
  decodeActiveAgentStatus,
  queryActiveAgentStatus,
} = require('../lib/agent-handoff.ts');

test('strict decoder accepts only the two canonical active-agent identities', () => {
  assert.deepEqual(
    decodeActiveAgentStatus(JSON.stringify(FINED_ACTIVE_AGENT_STATUS)),
    FINED_ACTIVE_AGENT_STATUS
  );
  assert.deepEqual(
    decodeActiveAgentStatus(JSON.stringify(TAXED_ACTIVE_AGENT_STATUS)),
    TAXED_ACTIVE_AGENT_STATUS
  );
});

test('strict decoder rejects noncanonical shape, identity, version and UTF-8 size', () => {
  const fines = { ...FINED_ACTIVE_AGENT_STATUS };
  const taxed = { ...TAXED_ACTIVE_AGENT_STATUS };
  for (const candidate of [
    { ...fines, caller: 'learner-1' },
    { ...fines, version: true },
    { ...fines, version: 1.5 },
    { ...fines, version: 2 },
    { ...fines, active_agent: 'taxed' },
    { ...taxed, display_name: 'FinEd Saathi' },
    { ...taxed, voice_name: 'Nikhil' },
    { ...taxed, specialty: null },
    { ...fines, specialty: 'Investment Tax Specialist' },
    { ...fines, display_name: 'FinEd Saathi\u0000' },
  ]) {
    assert.throws(() => decodeActiveAgentStatus(JSON.stringify(candidate)));
  }
  assert.throws(() => decodeActiveAgentStatus('x'.repeat(MAX_AGENT_STATUS_RPC_BYTES + 1)));
  assert.throws(() => decodeActiveAgentStatus('😀'.repeat(MAX_AGENT_STATUS_RPC_BYTES)));
});

test('RPC handler authorizes the connected backend agent before applying one status', async () => {
  const received = [];
  const handler = createAgentStatusRpcHandler('backend-agent', (status) => received.push(status));
  const taxedPayload = JSON.stringify(TAXED_ACTIVE_AGENT_STATUS);

  assert.equal(AGENT_STATUS_RPC_METHOD, 'fined.agent.v1.status');
  assert.equal(
    await handler({ callerIdentity: 'backend-agent', payload: taxedPayload }),
    '{"version":1,"accepted":true}'
  );
  assert.deepEqual(received, [TAXED_ACTIVE_AGENT_STATUS]);

  await assert.rejects(
    () => handler({ callerIdentity: 'other-participant', payload: taxedPayload }),
    /authorized/
  );
  assert.deepEqual(received, [TAXED_ACTIVE_AGENT_STATUS]);
});

test('status query asks only the connected backend participant for its canonical current state', async () => {
  const calls = [];
  const participant = {
    async performRpc(options) {
      calls.push(options);
      return JSON.stringify(TAXED_ACTIVE_AGENT_STATUS);
    },
  };

  assert.deepEqual(
    await queryActiveAgentStatus(participant, 'backend-agent'),
    TAXED_ACTIVE_AGENT_STATUS
  );
  assert.equal(AGENT_STATUS_QUERY_RPC_METHOD, 'fined.agent.v1.status.query');
  assert.deepEqual(calls, [
    {
      destinationIdentity: 'backend-agent',
      method: 'fined.agent.v1.status.query',
      payload: '{"version":1}',
      responseTimeout: 5_000,
    },
  ]);
});

test('status query rejects an invalid destination or noncanonical response', async () => {
  let calls = 0;
  const participant = {
    async performRpc() {
      calls += 1;
      return '{"version":1,"active_agent":"taxed","display_name":"TaxEd","voice_name":"Nikhil","specialty":null}';
    },
  };

  await assert.rejects(() => queryActiveAgentStatus(participant, ' '));
  assert.equal(calls, 0);
  await assert.rejects(() => queryActiveAgentStatus(participant, 'backend-agent'));
  assert.equal(calls, 1);
});
