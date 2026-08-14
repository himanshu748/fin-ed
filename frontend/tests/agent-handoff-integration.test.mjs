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

function createProviderHarness({ agentIdentity = 'backend-fined', registerError = null } = {}) {
  const states = [];
  const effects = [];
  const registrations = [];
  let stateCursor = 0;
  let effectCursor = 0;
  let pendingEffects = [];
  let currentIdentity = agentIdentity;
  const context = { current: null };
  const room = {
    registerRpcMethod(method, handler) {
      if (registerError) throw registerError;
      registrations.push({ method, handler });
    },
    unregisterRpcMethod(method) {
      registrations.push({ method, handler: null });
    },
  };
  const react = {
    createContext() {
      return context;
    },
    useCallback(callback) {
      return callback;
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
            isConnected: Boolean(currentIdentity),
            internal: { agentParticipant: currentIdentity ? { identity: currentIdentity } : null },
          }),
          useSessionContext: () => ({ room: { localParticipant: room } }),
        },
      ],
      ['@/lib/agent-handoff', require('../lib/agent-handoff.ts')],
    ])
  ).AgentHandoffProvider;

  function render() {
    stateCursor = 0;
    effectCursor = 0;
    pendingEffects = [];
    Provider({ children: null });
    for (const pending of pendingEffects) {
      effects[pending.index]?.cleanup?.();
      const cleanup = pending.effect();
      effects[pending.index] = {
        cleanup: typeof cleanup === 'function' ? cleanup : null,
        dependencies: pending.dependencies,
      };
    }
  }

  return {
    registrations,
    render,
    setAgentIdentity(identity) {
      currentIdentity = identity;
    },
    state() {
      return states[0];
    },
  };
}

test('provider scopes one status RPC to the current connected agent and resets on agent change', async () => {
  const harness = createProviderHarness();
  harness.render();
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

test('provider tolerates an RPC registration failure', () => {
  const harness = createProviderHarness({ registerError: new Error('room unavailable') });
  assert.doesNotThrow(() => harness.render());
  assert.equal(harness.state().voice_name, 'Nikhil');
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
