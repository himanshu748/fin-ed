import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8');
  const output = ts
    .transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      fileName: filename,
    })
    .outputText.replace(/require\((['"])(\.{1,2}\/[^'"]+)\1\)/g, 'require($1$2.ts$1)');
  module._compile(output, filename);
};

function loadProviderModule() {
  const filename = require.resolve('../components/paper-trading/paper-trading-provider.tsx');
  const source = require('node:fs').readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: filename,
  }).outputText;
  const compiledModule = { exports: {} };
  const dependencies = new Map([
    ['react', require('react')],
    ['react/jsx-runtime', require('react/jsx-runtime')],
    [
      '@livekit/components-react',
      { useAgent: () => ({ internal: { agentParticipant: null } }), useSessionContext: () => ({}) },
    ],
    ['@/lib/paper-trading/reducer', require('../lib/paper-trading/reducer.ts')],
    ['@/lib/paper-trading/schema', require('../lib/paper-trading/schema.ts')],
    ['@/lib/paper-trading/storage', require('../lib/paper-trading/storage.ts')],
  ]);

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected provider dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );
  return compiledModule.exports;
}

const {
  confirmPaperDraft,
  connectedAgentIdentity,
  connectedAgentSession,
  createPaperRpcHandlers,
  initializePaperLedger,
  reconcileAgentSession,
  reconcilePaperSave,
  registerPaperRpcHandlers,
  sendPaperOrderResult,
} = loadProviderModule();
const { createPaperPortfolio, reducePaperPortfolio } = require('../lib/paper-trading/reducer.ts');
const { decodePaperOrderDraft } = require('../lib/paper-trading/schema.ts');
const {
  PAPER_PORTFOLIO_STORAGE_KEY,
  savePaperPortfolio,
} = require('../lib/paper-trading/storage.ts');

const NOW = '2026-08-08T00:00:10.000Z';
const OPEN_REQUEST = '{"version":1,"paper":true}';

function draftPayload(overrides = {}) {
  return JSON.stringify({
    version: 1,
    paper: true,
    draft_id: 'draft-1',
    side: 'buy',
    exchange: 'NSE',
    symbol_token: '2885',
    trading_symbol: 'RELIANCE-EQ',
    quantity: 1,
    price_paise: 250_000,
    quote_provider: 'Angel One SmartAPI',
    quote_time: '2026-08-08T00:00:00.000Z',
    expires_at: '2026-08-08T00:00:30.000Z',
    notional_paise: 250_000,
    charge_paise: 100,
    cash_effect_paise: -250_100,
    charge_status: 'estimated',
    ...overrides,
  });
}

function harness(overrides = {}) {
  let opened = false;
  let prepared = null;
  let portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const handlers = createPaperRpcHandlers({
    expectedAgentIdentity: 'agent-1',
    expectedAgentSessionKey: 'agent-1:sid-a',
    getPortfolio: () => portfolio,
    getDraft: () => prepared,
    getReadiness: () => 'ready',
    now: () => NOW,
    openDashboard: () => {
      opened = true;
    },
    prepareDraft: (draft) => {
      prepared = draft;
    },
    ...overrides,
  });
  return {
    handlers,
    get opened() {
      return opened;
    },
    get prepared() {
      return prepared?.draft ?? null;
    },
    setPortfolio(value) {
      portfolio = value;
    },
  };
}

function invocation(payload, callerIdentity = 'agent-1') {
  return { callerIdentity, payload };
}

function memoryStorage(entries = {}) {
  const values = new Map(Object.entries(entries));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    putRaw(key, value) {
      values.set(key, value);
    },
  };
}

function locks() {
  let requestCount = 0;
  return {
    get requestCount() {
      return requestCount;
    },
    async request(name, options, callback) {
      assert.equal(name, PAPER_PORTFOLIO_STORAGE_KEY);
      assert.deepEqual(options, { mode: 'exclusive' });
      requestCount += 1;
      return callback();
    },
  };
}

test('open dashboard accepts only an exact request from the connected agent', async () => {
  const state = harness();

  assert.deepEqual(JSON.parse(await state.handlers.openDashboard(invocation(OPEN_REQUEST))), {
    version: 1,
    paper: true,
    opened: true,
  });
  assert.equal(state.opened, true);
  await assert.rejects(
    () => state.handlers.openDashboard(invocation(OPEN_REQUEST, 'other')),
    /authorized/
  );
  await assert.rejects(
    () => state.handlers.openDashboard(invocation('{"version":1,"paper":true,"secret":"x"}')),
    /shape/
  );
});

test('agent identity is available only from a connected LiveKit agent participant', () => {
  const participant = { identity: 'agent-1', sid: 'sid-a' };

  assert.equal(
    connectedAgentIdentity({ isConnected: true, internal: { agentParticipant: participant } }),
    'agent-1'
  );
  assert.equal(
    connectedAgentIdentity({ isConnected: false, internal: { agentParticipant: participant } }),
    null
  );
  assert.equal(
    connectedAgentIdentity({ isConnected: true, internal: { agentParticipant: null } }),
    null
  );
  assert.equal(
    connectedAgentSession({ isConnected: true, internal: { agentParticipant: participant } })
      .sessionKey,
    'agent-1:sid-a'
  );
  assert.notEqual(
    connectedAgentSession({ isConnected: true, internal: { agentParticipant: participant } })
      .sessionKey,
    connectedAgentSession({
      isConnected: true,
      internal: { agentParticipant: { identity: 'agent-1', sid: 'sid-b' } },
    }).sessionKey
  );
});

test('all handlers reject malformed, oversized, and lexically non-integer versions', async () => {
  const { handlers } = harness();
  const cases = [
    '{',
    '[]',
    '{"version":true,"paper":true}',
    '{"version":"1","paper":true}',
    '{"version":1.0,"paper":true}',
    '{"version":1e0,"paper":true}',
    '{"version":2,"paper":true}',
    JSON.stringify({ version: 1, paper: true, padding: '😀'.repeat(4_000) }),
  ];

  for (const payload of cases) {
    await assert.rejects(() => handlers.openDashboard(invocation(payload)));
    await assert.rejects(() => handlers.getPortfolioSummary(invocation(payload)));
  }
});

test('prepare order enforces the UTF-8 payload cap before accepting an exact draft shape', async () => {
  const { handlers } = harness();
  const oversized = draftPayload({ quote_provider: '😀'.repeat(4_000) });

  await assert.rejects(
    () => handlers.prepareOrder(invocation(oversized)),
    /exceeds the maximum size/
  );
});

test('prepare order rejects unexpected callers and unknown fields before changing the draft', async () => {
  const state = harness();
  const withSecret = JSON.parse(draftPayload());
  withSecret.secret = 'do-not-trust';

  await assert.rejects(
    () => state.handlers.prepareOrder(invocation(draftPayload(), 'other')),
    /authorized/
  );
  await assert.rejects(
    () => state.handlers.prepareOrder(invocation(JSON.stringify(withSecret))),
    /unknown or missing fields/
  );
  assert.equal(state.prepared, null);
});

test('prepare order rejects malformed values, duplicates, and expired drafts', async () => {
  const state = harness();
  const malformedCases = [
    draftPayload({ version: false }),
    draftPayload({ version: '1' }),
    draftPayload({ quantity: 1.5, notional_paise: 375_000, cash_effect_paise: -375_100 }),
    draftPayload({ paper: false }),
  ];

  for (const payload of malformedCases) {
    await assert.rejects(() => state.handlers.prepareOrder(invocation(payload)));
  }
  await assert.rejects(
    () =>
      state.handlers.prepareOrder(
        invocation(
          draftPayload({
            quote_time: '2026-08-07T23:59:40.000Z',
            expires_at: NOW,
          })
        )
      ),
    /expired/
  );

  const applied = reducePaperPortfolio(
    createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1'),
    {
      type: 'confirmDraft',
      draft: decodePaperOrderDraft(JSON.parse(draftPayload())),
      now: NOW,
    }
  );
  state.setPortfolio(applied);
  await assert.rejects(
    () => state.handlers.prepareOrder(invocation(draftPayload())),
    /already applied/
  );
});

test('prepare order opens the dashboard and returns only the strict draft acknowledgement', async () => {
  const state = harness();

  assert.deepEqual(JSON.parse(await state.handlers.prepareOrder(invocation(draftPayload()))), {
    version: 1,
    paper: true,
    prepared: true,
    draft_id: 'draft-1',
  });
  assert.equal(state.opened, true);
  assert.equal(state.prepared.draftId, 'draft-1');

  await assert.rejects(
    () => state.handlers.prepareOrder(invocation(draftPayload())),
    /already prepared/
  );
});

test('prepare order binds the draft to the authorized agent session', async () => {
  let preparedBinding = null;
  const state = harness({
    prepareDraft(binding) {
      preparedBinding = binding;
    },
  });

  await state.handlers.prepareOrder(invocation(draftPayload(), 'agent-1'));

  assert.equal(preparedBinding.agentIdentity, 'agent-1');
  assert.equal(preparedBinding.agentSessionKey, 'agent-1:sid-a');
  assert.equal(preparedBinding.draft.draftId, 'draft-1');
});

test('portfolio summary labels persisted holdings only as historical cost basis', async () => {
  const state = harness();
  const bought = reducePaperPortfolio(
    createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1'),
    { type: 'confirmDraft', draft: decodePaperOrderDraft(JSON.parse(draftPayload())), now: NOW }
  );
  state.setPortfolio(bought);

  assert.deepEqual(JSON.parse(await state.handlers.getPortfolioSummary(invocation(OPEN_REQUEST))), {
    version: 1,
    paper: true,
    cash_paise: 9_749_900,
    holdings_cost_basis_paise: 250_100,
    cash_plus_cost_basis_paise: 10_000_000,
  });
});

test('prepare and summary RPCs reject initializing, corrupt, and unavailable ledgers', async () => {
  for (const readiness of ['initializing', 'corrupt', 'unavailable']) {
    const state = harness({ getReadiness: () => readiness });

    await assert.rejects(
      () => state.handlers.prepareOrder(invocation(draftPayload())),
      /not ready/
    );
    await assert.rejects(
      () => state.handlers.getPortfolioSummary(invocation(OPEN_REQUEST)),
      /not ready/
    );
    assert.equal(state.prepared, null);
  }
});

test('ledger initialization is ready only after a coordinated real persistence result', async () => {
  const missingStorage = memoryStorage();
  const missingLocks = locks();
  const missing = await initializePaperLedger(missingStorage, missingLocks, NOW);
  assert.equal(missing.readiness, 'ready');
  assert.equal(missing.portfolio.cashPaise, 10_000_000);
  assert.equal(missingLocks.requestCount, 1);
  assert.notEqual(missingStorage.getItem(PAPER_PORTFOLIO_STORAGE_KEY), null);

  const noLocks = await initializePaperLedger(memoryStorage(), null, NOW);
  assert.equal(noLocks.readiness, 'unavailable');

  const throwingRead = await initializePaperLedger(
    {
      getItem() {
        throw new Error('private storage failure');
      },
      setItem() {
        throw new Error('private storage failure');
      },
    },
    locks(),
    NOW
  );
  assert.equal(throwingRead.readiness, 'unavailable');

  const throwingWrite = await initializePaperLedger(
    {
      getItem() {
        return null;
      },
      setItem() {
        throw new Error('private storage failure');
      },
    },
    locks(),
    NOW
  );
  assert.equal(throwingWrite.readiness, 'unavailable');

  const corrupt = await initializePaperLedger(
    memoryStorage({ [PAPER_PORTFOLIO_STORAGE_KEY]: '{' }),
    locks(),
    NOW
  );
  assert.equal(corrupt.readiness, 'corrupt');
});

test('a confirm write failure atomically downgrades readiness and closes later RPC access', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const draft = decodePaperOrderDraft(JSON.parse(draftPayload()));
  const result = await confirmPaperDraft({
    portfolio,
    draft,
    preparedAgentIdentity: 'agent-1',
    currentAgentIdentity: 'agent-1',
    preparedAgentSessionKey: 'agent-1:sid-a',
    currentAgentSessionKey: 'agent-1:sid-a',
    now: NOW,
    storage: {
      getItem() {
        return null;
      },
      setItem() {
        throw new Error('private write failure');
      },
    },
    coordinator: locks(),
    sendOrderResult() {
      return Promise.resolve('ack');
    },
  });
  const next = reconcilePaperSave(
    {
      readiness: 'ready',
      portfolio,
      draft: {
        draft,
        agentIdentity: 'agent-1',
        agentSessionKey: 'agent-1:sid-a',
      },
      error: null,
    },
    result,
    'confirm'
  );

  assert.equal(next.readiness, 'unavailable');
  assert.equal(next.portfolio.revision, 0);
  assert.equal(next.draft, null);
  assert.match(next.error, /persistence is unavailable/);
  const handlers = harness({ getReadiness: () => next.readiness }).handlers;
  await assert.rejects(() => handlers.prepareOrder(invocation(draftPayload())), /not ready/);
  await assert.rejects(() => handlers.getPortfolioSummary(invocation(OPEN_REQUEST)), /not ready/);
});

test('corruption discovered during reset atomically downgrades readiness', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const draft = decodePaperOrderDraft(JSON.parse(draftPayload()));
  const storage = memoryStorage({
    [PAPER_PORTFOLIO_STORAGE_KEY]: JSON.stringify(portfolio),
  });
  storage.putRaw(PAPER_PORTFOLIO_STORAGE_KEY, '{');
  const candidate = reducePaperPortfolio(portfolio, {
    type: 'reset',
    now: NOW,
  });
  const result = await savePaperPortfolio(storage, candidate, locks());
  const next = reconcilePaperSave(
    {
      readiness: 'ready',
      portfolio,
      draft: {
        draft,
        agentIdentity: 'agent-1',
        agentSessionKey: 'agent-1:sid-a',
      },
      error: null,
    },
    result,
    'reset'
  );

  assert.equal(next.readiness, 'corrupt');
  assert.equal(next.portfolio.revision, 0);
  assert.equal(next.draft, null);
  assert.match(next.error, /persistence is unavailable/);
});

test('RPC registration installs and cleans up all three methods exactly once', () => {
  const registered = [];
  const unregistered = [];
  const room = {
    registerRpcMethod(method, handler) {
      registered.push({ method, handler });
    },
    unregisterRpcMethod(method) {
      unregistered.push(method);
    },
  };
  const handlers = harness().handlers;

  const cleanup = registerPaperRpcHandlers(room, handlers);
  assert.deepEqual(
    registered.map(({ method }) => method),
    [
      'fined.paper.v1.open_dashboard',
      'fined.paper.v1.prepare_order',
      'fined.paper.v1.get_portfolio_summary',
    ]
  );
  cleanup();
  cleanup();
  assert.deepEqual(unregistered, [
    'fined.paper.v1.get_portfolio_summary',
    'fined.paper.v1.prepare_order',
    'fined.paper.v1.open_dashboard',
  ]);
});

test('partial RPC registration failure unregisters every installed method once', () => {
  const unregistered = [];
  const room = {
    registerRpcMethod(method) {
      if (method === 'fined.paper.v1.get_portfolio_summary') throw new Error('registration failed');
    },
    unregisterRpcMethod(method) {
      unregistered.push(method);
    },
  };

  assert.throws(() => registerPaperRpcHandlers(room, harness().handlers), /registration failed/);
  assert.deepEqual(unregistered, ['fined.paper.v1.prepare_order', 'fined.paper.v1.open_dashboard']);
});

test('confirmed fill persists through the lock and sends an exact result without awaiting voice ack', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const draft = decodePaperOrderDraft(JSON.parse(draftPayload()));
  const storage = memoryStorage();
  let rpcPayload;
  let resolveAck;
  const ack = new Promise((resolve) => {
    resolveAck = resolve;
  });

  const result = await confirmPaperDraft({
    portfolio,
    draft,
    preparedAgentIdentity: 'agent-1',
    currentAgentIdentity: 'agent-1',
    preparedAgentSessionKey: 'agent-1:sid-a',
    currentAgentSessionKey: 'agent-1:sid-a',
    now: NOW,
    storage,
    coordinator: locks(),
    sendOrderResult(payload) {
      rpcPayload = payload;
      return ack;
    },
  });

  assert.equal(result.status, 'saved');
  assert.equal(result.portfolio.revision, 1);
  assert.deepEqual(rpcPayload, {
    version: 1,
    paper: true,
    draft_id: 'draft-1',
    side: 'buy',
    trading_symbol: 'RELIANCE-EQ',
    quantity: 1,
    fill_price_paise: 250_000,
    simulated_at: '2026-08-08T00:00:10.000+00:00',
    cash_paise: 9_749_900,
  });
  resolveAck('{"version":1,"paper":true,"acknowledged":true}');
});

test('a replacement agent cannot confirm or receive a draft prepared by the prior session', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const storage = memoryStorage();
  let resultCalls = 0;

  await assert.rejects(
    () =>
      confirmPaperDraft({
        portfolio,
        draft: decodePaperOrderDraft(JSON.parse(draftPayload())),
        preparedAgentIdentity: 'agent-1',
        currentAgentIdentity: 'agent-2',
        preparedAgentSessionKey: 'agent-1:sid-a',
        currentAgentSessionKey: 'agent-2:sid-b',
        now: NOW,
        storage,
        coordinator: locks(),
        sendOrderResult() {
          resultCalls += 1;
          return Promise.resolve('ack');
        },
      }),
    /different agent session/
  );

  assert.equal(storage.getItem(PAPER_PORTFOLIO_STORAGE_KEY), null);
  assert.equal(portfolio.revision, 0);
  assert.equal(resultCalls, 0);
});

test('same-identity participant replacement cannot confirm the prior SID draft', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const storage = memoryStorage();
  let resultCalls = 0;

  await assert.rejects(
    () =>
      confirmPaperDraft({
        portfolio,
        draft: decodePaperOrderDraft(JSON.parse(draftPayload())),
        preparedAgentIdentity: 'agent-1',
        currentAgentIdentity: 'agent-1',
        preparedAgentSessionKey: 'agent-1:sid-a',
        currentAgentSessionKey: 'agent-1:sid-b',
        now: NOW,
        storage,
        coordinator: locks(),
        sendOrderResult() {
          resultCalls += 1;
          return Promise.resolve('ack');
        },
      }),
    /different agent session/
  );

  assert.equal(storage.getItem(PAPER_PORTFOLIO_STORAGE_KEY), null);
  assert.equal(portfolio.revision, 0);
  assert.equal(resultCalls, 0);
});

test('provider lifecycle clears a bound draft when only the participant SID changes', () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const draft = decodePaperOrderDraft(JSON.parse(draftPayload()));

  const reconnected = reconcileAgentSession(
    {
      readiness: 'ready',
      portfolio,
      draft: {
        draft,
        agentIdentity: 'agent-1',
        agentSessionKey: 'agent-1:sid-a',
      },
      error: null,
    },
    'agent-1:sid-b'
  );

  assert.equal(reconnected.draft, null);
  assert.equal(reconnected.readiness, 'ready');
  assert.equal(reconnected.portfolio, portfolio);
});

test('result RPC targets only the connected agent with the backend-compatible flat payload', async () => {
  const calls = [];
  const localParticipant = {
    performRpc(options) {
      calls.push(options);
      return Promise.resolve('ack');
    },
  };
  const payload = {
    version: 1,
    paper: true,
    draft_id: 'draft-1',
    side: 'buy',
    trading_symbol: 'RELIANCE-EQ',
    quantity: 1,
    fill_price_paise: 250_000,
    simulated_at: '2026-08-08T00:00:10.000+00:00',
    cash_paise: 9_749_900,
  };

  await sendPaperOrderResult(localParticipant, 'agent-1', payload);

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], {
    destinationIdentity: 'agent-1',
    method: 'fined.paper.v1.order_result',
    payload: JSON.stringify(payload),
    responseTimeout: 10_000,
  });
});

test('a stale save returns the winning portfolio and never reports the losing draft', async () => {
  const initial = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  const winner = reducePaperPortfolio(initial, {
    type: 'reset',
    now: '2026-08-08T00:00:05.000Z',
  });
  const storage = memoryStorage({
    [PAPER_PORTFOLIO_STORAGE_KEY]: JSON.stringify(winner),
  });
  let resultCalls = 0;

  const result = await confirmPaperDraft({
    portfolio: initial,
    draft: decodePaperOrderDraft(JSON.parse(draftPayload())),
    preparedAgentIdentity: 'agent-1',
    currentAgentIdentity: 'agent-1',
    preparedAgentSessionKey: 'agent-1:sid-a',
    currentAgentSessionKey: 'agent-1:sid-a',
    now: NOW,
    storage,
    coordinator: locks(),
    sendOrderResult() {
      resultCalls += 1;
      return Promise.resolve('ack');
    },
  });

  assert.deepEqual(result, { status: 'stale', portfolio: winner });
  assert.equal(resultCalls, 0);
});

test('unavailable persistence fails safely without applying or reporting a fill', async () => {
  const portfolio = createPaperPortfolio('2026-08-08T00:00:00.000Z', 'portfolio-1');
  let resultCalls = 0;

  const result = await confirmPaperDraft({
    portfolio,
    draft: decodePaperOrderDraft(JSON.parse(draftPayload())),
    preparedAgentIdentity: 'agent-1',
    currentAgentIdentity: 'agent-1',
    preparedAgentSessionKey: 'agent-1:sid-a',
    currentAgentSessionKey: 'agent-1:sid-a',
    now: NOW,
    storage: memoryStorage(),
    coordinator: null,
    sendOrderResult() {
      resultCalls += 1;
      return Promise.resolve('ack');
    },
  });

  assert.deepEqual(result, { status: 'unavailable' });
  assert.equal(portfolio.revision, 0);
  assert.equal(resultCalls, 0);
});

test('App places PaperTradingProvider inside AgentSessionProvider around the session UI', () => {
  const filename = require.resolve('../components/app/app.tsx');
  const source = require('node:fs').readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: filename,
  }).outputText;
  const compiledModule = { exports: {} };
  const AgentSessionProvider = Symbol('AgentSessionProvider');
  const PaperTradingProvider = Symbol('PaperTradingProvider');
  const ViewController = Symbol('ViewController');
  const jsxRuntime = {
    Fragment: Symbol('Fragment'),
    jsx: (type, props) => ({ type, props }),
    jsxs: (type, props) => ({ type, props }),
  };
  const dependencies = new Map([
    [
      'react',
      {
        useMemo: (factory) => factory(),
        useState: (initial) => [initial, () => undefined],
      },
    ],
    ['react/jsx-runtime', jsxRuntime],
    ['@livekit/components-react', { useSession: () => ({ room: {} }) }],
    ['@/components/agents-ui/agent-session-provider', { AgentSessionProvider }],
    ['@/components/agents-ui/start-audio-button', { StartAudioButton: Symbol('StartAudioButton') }],
    ['@/components/app/view-controller', { ViewController }],
    ['@/components/paper-trading/paper-trading-provider', { PaperTradingProvider }],
    ['@/hooks/useDebug', { useDebugMode: () => undefined }],
    ['@/lib/learning-modes', { participantMetadataForLearningMode: () => 'metadata' }],
    ['@/lib/utils', { createModeScopedTokenSource: () => 'token-source' }],
  ]);

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected App dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );
  const tree = compiledModule.exports.App({ appConfig: {} });

  assert.equal(tree.type, AgentSessionProvider);
  assert.equal(tree.props.children.type, PaperTradingProvider);
  const paperChildren = tree.props.children.props.children;
  assert.ok(paperChildren.some((child) => child?.props?.children?.type === ViewController));
});
