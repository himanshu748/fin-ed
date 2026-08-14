import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const frontendRoot = join(import.meta.dirname, '..');
const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = readFileSync(filename, 'utf8');
  module._compile(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      fileName: filename,
    }).outputText,
    filename
  );
};

function compile(relativePath, dependencies) {
  const output = ts.transpileModule(readFileSync(join(frontendRoot, relativePath), 'utf8'), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const compiledModule = { exports: {} };
  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected ${relativePath} dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );
  return compiledModule.exports;
}

function dependenciesChanged(previous, next) {
  if (previous === undefined || next === undefined || previous.length !== next.length) return true;
  return previous.some((value, index) => !Object.is(value, next[index]));
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const FINED_RESPONSE = JSON.stringify({
  version: 1,
  active_agent: 'fined',
  display_name: 'FinEd Saathi',
  voice_name: 'Nikhil',
  specialty: null,
});
const TAXED_RESPONSE = JSON.stringify({
  version: 1,
  active_agent: 'taxed',
  display_name: 'TaxEd',
  voice_name: 'Anusha',
  specialty: 'Investment Tax Specialist',
});

function createProviderHarness({
  agentIdentity = 'backend-fined',
  agentSid = 'PA_fined_1',
  registerError = null,
  queryResponses = [FINED_RESPONSE],
} = {}) {
  const states = [];
  const refs = [];
  const effects = [];
  const callbacks = [];
  const registrations = [];
  const queries = [];
  let stateCursor = 0;
  let refCursor = 0;
  let callbackCursor = 0;
  let effectCursor = 0;
  let pendingEffects = [];
  let currentAgent = agentIdentity ? { identity: agentIdentity, sid: agentSid } : null;
  let queryResponseIndex = 0;
  const context = { current: null };
  const room = {
    registerRpcMethod(method, handler) {
      if (registerError) throw registerError;
      registrations.push({ method, handler });
    },
    unregisterRpcMethod(method) {
      registrations.push({ method, handler: null });
    },
    async performRpc(options) {
      queries.push(options);
      const response = queryResponses[queryResponseIndex++] ?? FINED_RESPONSE;
      if (response instanceof Error) throw response;
      return await response;
    },
  };
  const react = {
    createContext() {
      return context;
    },
    useCallback(callback, dependencies) {
      const index = callbackCursor++;
      if (dependenciesChanged(callbacks[index]?.dependencies, dependencies)) {
        callbacks[index] = { callback, dependencies };
      }
      return callbacks[index].callback;
    },
    useContext() {
      return context.current;
    },
    useEffect(effect, dependencies) {
      const index = effectCursor++;
      if (dependenciesChanged(effects[index]?.dependencies, dependencies)) {
        pendingEffects.push({ index, effect, dependencies });
      }
    },
    useMemo(factory) {
      return factory();
    },
    useRef(initialValue) {
      const index = refCursor++;
      if (!(index in refs)) refs[index] = { current: initialValue };
      return refs[index];
    },
    useState(initialValue) {
      const index = stateCursor++;
      if (!(index in states)) states[index] = initialValue;
      return [
        states[index],
        (value) => (states[index] = typeof value === 'function' ? value(states[index]) : value),
      ];
    },
  };
  const Provider = compile(
    'components/agent-handoff/agent-handoff-provider.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', { jsx: (type, props) => ({ type, props }) }],
      [
        '@livekit/components-react',
        {
          useAgent: () => ({
            isConnected: currentAgent !== null,
            internal: { agentParticipant: currentAgent },
          }),
          useSessionContext: () => ({ room: { localParticipant: room } }),
        },
      ],
      ['@/lib/agent-handoff', require('../lib/agent-handoff.ts')],
    ])
  ).AgentHandoffProvider;

  function render() {
    stateCursor = 0;
    refCursor = 0;
    callbackCursor = 0;
    effectCursor = 0;
    pendingEffects = [];
    Provider({ children: null });
    for (const pending of pendingEffects) {
      effects[pending.index]?.cleanup?.();
      const cleanup = pending.effect();
      effects[pending.index] = {
        cleanup: typeof cleanup === 'function' ? cleanup : null,
        dependencies: pending.dependencies,
        effect: pending.effect,
      };
    }
  }

  return {
    registrations,
    queries,
    render,
    setAgentIdentity(identity) {
      currentAgent = identity ? { identity, sid: currentAgent?.sid ?? 'PA_fined_1' } : null;
    },
    replaceAgentParticipant({ identity, sid }) {
      currentAgent = { identity, sid };
    },
    strictModeReplayEffects() {
      for (const record of effects) record?.cleanup?.();
      for (let index = 0; index < effects.length; index += 1) {
        const record = effects[index];
        if (!record) continue;
        const cleanup = record.effect();
        effects[index] = { ...record, cleanup: typeof cleanup === 'function' ? cleanup : null };
      }
    },
    async settleQueries() {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
    state() {
      return states[0];
    },
  };
}

test('provider scopes one status RPC to the current connected agent and resets on agent change', async () => {
  const harness = createProviderHarness();
  harness.render();
  await harness.settleQueries();
  assert.equal(harness.registrations.length, 1);
  assert.equal(harness.registrations[0].method, 'fined.agent.v1.status');

  await harness.registrations[0].handler({
    callerIdentity: 'backend-fined',
    payload: JSON.stringify({
      version: 1,
      active_agent: 'taxed',
      display_name: 'TaxEd',
      voice_name: 'Anusha',
      specialty: 'Investment Tax Specialist',
    }),
  });
  harness.render();
  assert.equal(harness.state().display_name, 'TaxEd');

  harness.setAgentIdentity('backend-taxed');
  harness.render();
  assert.equal(harness.registrations[1].method, 'fined.agent.v1.status');
  assert.equal(harness.registrations[2].method, 'fined.agent.v1.status');
  assert.equal(harness.state().display_name, 'FinEd Saathi');
});

test('same-identity participant replacement resets status and replaces the scoped RPC once', async () => {
  const harness = createProviderHarness({ queryResponses: [FINED_RESPONSE, TAXED_RESPONSE] });
  harness.render();
  await harness.settleQueries();
  await harness.registrations[0].handler({
    callerIdentity: 'backend-fined',
    payload: JSON.stringify({
      version: 1,
      active_agent: 'taxed',
      display_name: 'TaxEd',
      voice_name: 'Anusha',
      specialty: 'Investment Tax Specialist',
    }),
  });
  harness.render();
  assert.equal(harness.state().display_name, 'TaxEd');

  harness.replaceAgentParticipant({ identity: 'backend-fined', sid: 'PA_fined_2' });
  harness.render();

  assert.equal(harness.state().display_name, 'FinEd Saathi');
  assert.deepEqual(
    harness.registrations.map(({ method, handler }) => ({ method, registered: handler !== null })),
    [
      { method: 'fined.agent.v1.status', registered: true },
      { method: 'fined.agent.v1.status', registered: false },
      { method: 'fined.agent.v1.status', registered: true },
    ]
  );
  await harness.settleQueries();
  assert.equal(harness.state().display_name, 'TaxEd');
  assert.equal(harness.queries.length, 2);
});

test('a status update on the same participant SID preserves one provider registration', async () => {
  const harness = createProviderHarness();
  harness.render();
  await harness.settleQueries();
  await harness.registrations[0].handler({
    callerIdentity: 'backend-fined',
    payload: JSON.stringify({
      version: 1,
      active_agent: 'taxed',
      display_name: 'TaxEd',
      voice_name: 'Anusha',
      specialty: 'Investment Tax Specialist',
    }),
  });
  harness.render();

  assert.equal(harness.state().display_name, 'TaxEd');
  assert.equal(harness.registrations.length, 1);
  assert.equal(harness.queries.length, 1);
});

test('an authorized push invalidates an older status query for the same participant', async () => {
  const stale = deferred();
  const harness = createProviderHarness({ queryResponses: [stale.promise] });
  harness.render();

  await harness.registrations[0].handler({
    callerIdentity: 'backend-fined',
    payload: TAXED_RESPONSE,
  });
  harness.render();
  assert.equal(harness.state().display_name, 'TaxEd');

  stale.resolve(FINED_RESPONSE);
  await harness.settleQueries();

  assert.equal(harness.state().display_name, 'TaxEd');
  assert.equal(harness.queries.length, 1);
  assert.equal(harness.registrations.length, 1);
});

test('Strict Mode replay cleans the prior RPC and leaves one replacement registration', () => {
  const harness = createProviderHarness();
  harness.render();

  harness.strictModeReplayEffects();

  assert.deepEqual(
    harness.registrations.map(({ method, handler }) => ({ method, registered: handler !== null })),
    [
      { method: 'fined.agent.v1.status', registered: true },
      { method: 'fined.agent.v1.status', registered: false },
      { method: 'fined.agent.v1.status', registered: true },
    ]
  );
});

test('a fresh FinEd participant replaces a previously queried TaxEd status', async () => {
  const harness = createProviderHarness({ queryResponses: [TAXED_RESPONSE, FINED_RESPONSE] });
  harness.render();
  await harness.settleQueries();
  assert.equal(harness.state().display_name, 'TaxEd');

  harness.replaceAgentParticipant({ identity: 'backend-fined', sid: 'PA_fined_2' });
  harness.render();
  await harness.settleQueries();

  assert.equal(harness.state().display_name, 'FinEd Saathi');
  assert.equal(harness.queries.length, 2);
});

test('query failure leaves the safe FinEd default without crashing', async () => {
  const harness = createProviderHarness({
    queryResponses: [new Error('private transport failure')],
  });

  harness.render();
  await harness.settleQueries();

  assert.equal(harness.state().display_name, 'FinEd Saathi');
  assert.equal(harness.queries.length, 1);
});

test('out-of-order query completion cannot restore status from a prior participant SID', async () => {
  const stale = deferred();
  const current = deferred();
  const harness = createProviderHarness({
    queryResponses: [stale.promise, current.promise],
  });
  harness.render();
  harness.replaceAgentParticipant({ identity: 'backend-fined', sid: 'PA_fined_2' });
  harness.render();

  current.resolve(TAXED_RESPONSE);
  await harness.settleQueries();
  assert.equal(harness.state().display_name, 'TaxEd');
  stale.resolve(FINED_RESPONSE);
  await harness.settleQueries();

  assert.equal(harness.state().display_name, 'TaxEd');
});

test('Strict Mode replay ignores its stale query and leaves one live handler', async () => {
  const stale = deferred();
  const current = deferred();
  const harness = createProviderHarness({
    queryResponses: [stale.promise, current.promise],
  });
  harness.render();
  harness.strictModeReplayEffects();

  current.resolve(TAXED_RESPONSE);
  await harness.settleQueries();
  stale.resolve(FINED_RESPONSE);
  await harness.settleQueries();

  assert.equal(harness.state().display_name, 'TaxEd');
  assert.deepEqual(
    harness.registrations.map(({ method, handler }) => ({ method, registered: handler !== null })),
    [
      { method: 'fined.agent.v1.status', registered: true },
      { method: 'fined.agent.v1.status', registered: false },
      { method: 'fined.agent.v1.status', registered: true },
    ]
  );
  assert.equal(harness.queries.length, 2);
});

test('provider tolerates an RPC registration failure', () => {
  const harness = createProviderHarness({ registerError: new Error('room unavailable') });
  assert.doesNotThrow(() => harness.render());
  assert.equal(harness.state().voice_name, 'Nikhil');
  assert.equal(harness.queries.length, 0);
});

test('badge announces a validated identity without animation', () => {
  const badge = compile(
    'components/agent-handoff/active-agent-badge.tsx',
    new Map([
      [
        'react/jsx-runtime',
        {
          jsx: (type, props) => ({ type, props }),
          jsxs: (type, props) => ({ type, props }),
        },
      ],
      [
        '@/components/agent-handoff/agent-handoff-provider',
        {
          useAgentHandoff: () => ({
            activeAgent: {
              version: 1,
              active_agent: 'taxed',
              display_name: 'TaxEd',
              voice_name: 'Anusha',
              specialty: 'Investment Tax Specialist',
            },
          }),
        },
      ],
    ])
  ).ActiveAgentBadge();
  assert.equal(badge.props.role, 'status');
  assert.equal(badge.props['aria-live'], 'polite');
  assert.doesNotMatch(badge.props.className, /animate|transition/);
});
