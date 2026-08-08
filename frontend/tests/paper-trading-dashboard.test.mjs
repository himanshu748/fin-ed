import * as React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as jsxRuntime from 'react/jsx-runtime';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';
import * as Dialog from '@radix-ui/react-dialog';

const frontendRoot = join(import.meta.dirname, '..');

function read(relativePath) {
  const path = join(frontendRoot, relativePath);
  return existsSync(path) ? readFileSync(path, 'utf8') : '';
}

function includesAll(source, values, message) {
  for (const value of values) {
    assert.ok(source.includes(value), `${message}: ${value}`);
  }
}

const icon = ({ children, ...props }) => React.createElement('span', props, children);
const iconModule = new Proxy({}, { get: () => icon });
const image = ({ alt, ...props }) => React.createElement('img', { alt, ...props });

function compile(relativePath, dependencies) {
  const source = read(relativePath);
  assert.ok(source, `${relativePath} must exist`);
  const output = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: join(frontendRoot, relativePath),
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

function loadPortfolioSummary(react = React, useAnimatedNumber = (value) => value) {
  return compile(
    'components/paper-trading/portfolio-summary.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', jsxRuntime],
      ['@/hooks/use-animated-number', { useAnimatedNumber }],
    ])
  );
}

function loadOrderReview(
  react = React,
  { animate = () => ({ cancel() {} }), reduceMotion = true } = {}
) {
  const common = new Map([
    ['react', react],
    ['react/jsx-runtime', jsxRuntime],
    ['next/image', { default: image }],
    ['animejs', { animate }],
    ['motion/react', { useReducedMotion: () => reduceMotion }],
    ['@/hooks/use-animated-number', { useAnimatedNumber: (value) => value }],
  ]);
  const portfolioSummary = compile('components/paper-trading/portfolio-summary.tsx', common);
  common.set('@/components/paper-trading/portfolio-summary', portfolioSummary);
  return compile('components/paper-trading/order-review.tsx', common);
}

function statefulReact(refCurrents = []) {
  const states = [];
  const refs = [];
  const effectRecords = [];
  let stateCursor = 0;
  let refCursor = 0;
  let effectCursor = 0;
  let pendingEffects = [];

  function dependenciesChanged(previous, next) {
    if (previous === undefined || next === undefined || previous.length !== next.length)
      return true;
    return previous.some((value, index) => !Object.is(value, next[index]));
  }

  function flushEffects() {
    for (const pending of pendingEffects) {
      effectRecords[pending.index]?.cleanup?.();
      const cleanup = pending.effect();
      effectRecords[pending.index] = {
        cleanup: typeof cleanup === 'function' ? cleanup : null,
        dependencies: pending.dependencies,
        effect: pending.effect,
      };
    }
    pendingEffects = [];
  }

  return {
    react: {
      ...React,
      useEffect(effect, dependencies) {
        const index = effectCursor;
        effectCursor += 1;
        if (dependenciesChanged(effectRecords[index]?.dependencies, dependencies)) {
          pendingEffects.push({ index, effect, dependencies });
        }
      },
      useLayoutEffect(effect, dependencies) {
        const index = effectCursor;
        effectCursor += 1;
        if (dependenciesChanged(effectRecords[index]?.dependencies, dependencies)) {
          pendingEffects.push({ index, effect, dependencies });
        }
      },
      useRef(initialValue) {
        const index = refCursor;
        refCursor += 1;
        if (!(index in refs)) {
          refs[index] = {
            current: index in refCurrents ? refCurrents[index] : initialValue,
          };
        }
        return refs[index];
      },
      useState(initialValue) {
        const index = stateCursor;
        stateCursor += 1;
        if (!(index in states)) {
          states[index] = typeof initialValue === 'function' ? initialValue() : initialValue;
        }
        return [
          states[index],
          (value) => {
            states[index] = typeof value === 'function' ? value(states[index]) : value;
          },
        ];
      },
    },
    render(Component, props) {
      stateCursor = 0;
      refCursor = 0;
      effectCursor = 0;
      pendingEffects = [];
      const element = Component(props);
      flushEffects();
      return element;
    },
    renderBeforeEffects(Component, props) {
      stateCursor = 0;
      refCursor = 0;
      effectCursor = 0;
      pendingEffects = [];
      return Component(props);
    },
    flushEffects,
    strictModeReplayEffects() {
      for (const record of effectRecords) record?.cleanup?.();
      for (let index = 0; index < effectRecords.length; index += 1) {
        const record = effectRecords[index];
        if (!record) continue;
        const cleanup = record.effect();
        effectRecords[index] = {
          ...record,
          cleanup: typeof cleanup === 'function' ? cleanup : null,
        };
      }
    },
    unmount() {
      for (const record of effectRecords) record?.cleanup?.();
      effectRecords.length = 0;
    },
  };
}

function fakeBrowserClock(initialNow, initiallyHidden = false) {
  const originalDateNow = Date.now;
  const originalDocument = globalThis.document;
  const hadDocument = 'document' in globalThis;
  const originalSetInterval = globalThis.setInterval;
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearInterval = globalThis.clearInterval;
  const originalClearTimeout = globalThis.clearTimeout;
  const timeouts = new Map();
  const intervals = new Map();
  const visibilityListeners = new Set();
  let nextTimerId = 1;
  let now = initialNow;
  let hidden = initiallyHidden;
  let intervalCalls = 0;

  Date.now = () => now;
  globalThis.document = {
    get hidden() {
      return hidden;
    },
    addEventListener(name, listener) {
      if (name === 'visibilitychange') visibilityListeners.add(listener);
    },
    removeEventListener(name, listener) {
      if (name === 'visibilitychange') visibilityListeners.delete(listener);
    },
  };
  globalThis.setTimeout = (callback, delay) => {
    const id = nextTimerId;
    nextTimerId += 1;
    timeouts.set(id, { callback, delay });
    return id;
  };
  globalThis.clearTimeout = (id) => {
    timeouts.delete(id);
  };
  globalThis.setInterval = (callback, delay) => {
    intervalCalls += 1;
    const id = nextTimerId;
    nextTimerId += 1;
    intervals.set(id, { callback, delay });
    return id;
  };
  globalThis.clearInterval = (id) => {
    intervals.delete(id);
  };

  return {
    activeTimerCount() {
      return timeouts.size + intervals.size;
    },
    intervalCallCount() {
      return intervalCalls;
    },
    nextTimeoutDelay() {
      return timeouts.values().next().value?.delay ?? null;
    },
    runNextTimeout() {
      const next = timeouts.entries().next().value;
      assert.ok(next, 'an active timeout is required');
      const [id, timer] = next;
      timeouts.delete(id);
      now += timer.delay;
      timer.callback();
    },
    setNow(value) {
      now = value;
    },
    setHidden(value) {
      hidden = value;
      for (const listener of [...visibilityListeners]) listener();
    },
    visibilityListenerCount() {
      return visibilityListeners.size;
    },
    restore() {
      Date.now = originalDateNow;
      if (hadDocument) globalThis.document = originalDocument;
      else delete globalThis.document;
      globalThis.setInterval = originalSetInterval;
      globalThis.setTimeout = originalSetTimeout;
      globalThis.clearInterval = originalClearInterval;
      globalThis.clearTimeout = originalClearTimeout;
    },
  };
}

function loadSessionViewForFocus(react, paperTrading) {
  const connectionState = {
    Reconnecting: 'reconnecting',
    SignalReconnecting: 'signal-reconnecting',
    Connected: 'connected',
  };
  return compile(
    'components/app/fin-ed-session-view.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', jsxRuntime],
      ['gsap', { gsap: {} }],
      ['livekit-client', { ConnectionState: connectionState }],
      ['lucide-react', iconModule],
      ['motion/react', { useReducedMotion: () => true }],
      [
        '@livekit/components-react',
        {
          useAgent: () => ({ state: 'idle' }),
          useSessionContext: () => ({
            connectionState: connectionState.Connected,
            isConnected: true,
          }),
          useSessionMessages: () => ({ messages: [] }),
          useVoiceAssistant: () => ({ audioTrack: undefined }),
        },
      ],
      [
        '@/components/agents-ui/agent-audio-visualizer-bar',
        { AgentAudioVisualizerBar: () => null },
      ],
      ['@/components/agents-ui/agent-chat-transcript', { AgentChatTranscript: () => null }],
      ['@/components/agents-ui/agent-control-bar', { AgentControlBar: () => null }],
      ['@/components/paper-trading/paper-trading-dashboard', { PaperTradingDashboard: () => null }],
      [
        '@/components/paper-trading/paper-trading-provider',
        { usePaperTrading: () => paperTrading },
      ],
      ['@/lib/learning-modes', { LEARNING_MODES: [{ value: 'general', label: 'Ask Anything' }] }],
    ])
  ).FinEdSessionView;
}

function textContent(node) {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textContent).join('');
  return textContent(node.props?.children);
}

function findElement(node, predicate) {
  if (node === null || node === undefined || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findElement(child, predicate);
      if (found) return found;
    }
    return null;
  }
  if (predicate(node)) return node;
  return findElement(node.props?.children, predicate);
}

function loadDashboardForInteraction(react, context) {
  return compile(
    'components/paper-trading/paper-trading-dashboard.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', jsxRuntime],
      ['lucide-react', iconModule],
      ['@radix-ui/react-dialog', Dialog],
      ['@/components/paper-trading/activity-ledger', { ActivityLedger: () => null }],
      ['@/components/paper-trading/holdings-ledger', { HoldingsLedger: () => null }],
      ['@/components/paper-trading/order-review', { OrderReview: () => null }],
      ['@/components/paper-trading/portfolio-summary', { PortfolioSummary: () => null }],
      ['@/components/paper-trading/paper-trading-provider', { usePaperTrading: () => context }],
    ])
  ).PaperTradingDashboard;
}

function portfolio(overrides = {}) {
  return {
    schemaVersion: 1,
    portfolioId: 'portfolio-1',
    revision: 2,
    startingCashPaise: 10_000_000,
    cashPaise: 7_049_300,
    holdings: [
      {
        exchange: 'NSE',
        symbolToken: '2885',
        tradingSymbol: 'RELIANCE-EQ',
        quantity: 1,
        costBasisPaise: 2_950_700,
        averageCostPaise: 2_950_700,
      },
    ],
    fills: [
      {
        draftId: 'filled-1',
        side: 'sell',
        exchange: 'NSE',
        symbolToken: '1594',
        tradingSymbol: 'INFY-EQ',
        quantity: 1,
        fillPricePaise: 150_000,
        notionalPaise: 150_000,
        chargesPaise: 100,
        cashEffectPaise: 149_900,
        realizedPnlPaise: -5_100,
        filledAt: '2026-08-08T09:30:00.000Z',
      },
    ],
    appliedDraftIds: ['filled-1'],
    createdAt: '2026-08-08T09:00:00.000Z',
    updatedAt: '2026-08-08T09:30:00.000Z',
    ...overrides,
  };
}

function draft(overrides = {}) {
  return {
    draftId: 'draft-1',
    side: 'buy',
    exchange: 'NSE',
    symbolToken: '2885',
    tradingSymbol: 'RELIANCE-EQ',
    quantity: 1,
    pricePaise: 2_950_500,
    quoteProvider: 'Angel One SmartAPI',
    quoteTime: '2026-08-08T09:31:00.000Z',
    expiresAt: '2999-08-08T09:32:00.000Z',
    notionalPaise: 2_950_500,
    chargePaise: 200,
    cashEffectPaise: -2_950_700,
    chargeStatus: 'estimated',
    ...overrides,
  };
}

function renderDashboard(overrides = {}) {
  const context = {
    view: 'dashboard',
    readiness: 'ready',
    portfolio: portfolio(),
    draft: draft(),
    error: null,
    openDashboard() {},
    closeDashboard() {},
    async confirmDraft() {
      return true;
    },
    async resetPortfolio() {
      return true;
    },
    ...overrides,
  };
  const common = new Map([
    ['react', React],
    ['react/jsx-runtime', jsxRuntime],
    ['lucide-react', iconModule],
    ['@radix-ui/react-dialog', Dialog],
    ['next/image', { default: image }],
    ['animejs', { animate: () => ({ cancel() {} }) }],
    ['motion/react', { useReducedMotion: () => true }],
    ['@/hooks/use-animated-number', { useAnimatedNumber: (value) => value }],
  ]);
  const portfolioSummary = compile('components/paper-trading/portfolio-summary.tsx', common);
  common.set('@/components/paper-trading/portfolio-summary', portfolioSummary);
  const holdingsLedger = compile('components/paper-trading/holdings-ledger.tsx', common);
  const activityLedger = compile('components/paper-trading/activity-ledger.tsx', common);
  const orderReview = loadOrderReview();
  const dashboard = compile(
    'components/paper-trading/paper-trading-dashboard.tsx',
    new Map([
      ...common,
      ['@/components/paper-trading/paper-trading-provider', { usePaperTrading: () => context }],
      ['@/components/paper-trading/portfolio-summary', portfolioSummary],
      ['@/components/paper-trading/holdings-ledger', holdingsLedger],
      ['@/components/paper-trading/activity-ledger', activityLedger],
      ['@/components/paper-trading/order-review', orderReview],
    ])
  );
  return renderToStaticMarkup(React.createElement(dashboard.PaperTradingDashboard));
}

test('paper dashboard states the safety boundary and exact confirmation', () => {
  const source = [
    read('components/paper-trading/paper-trading-dashboard.tsx'),
    read('components/paper-trading/order-review.tsx'),
  ].join('\n');

  includesAll(
    source,
    [
      'Paper trading only',
      'No real money or broker account',
      'Confirm paper buy',
      'Confirm paper sell',
      'This updates only your practice portfolio.',
      'Back to learning',
    ],
    'missing paper safety copy'
  );
});

test('the no-draft review reserves responsive space for concise empty-ledger artwork', () => {
  const { OrderReview } = loadOrderReview();
  const markup = renderToStaticMarkup(
    React.createElement(OrderReview, {
      draft: null,
      portfolio: portfolio(),
      readiness: 'ready',
      onConfirm: async () => true,
    })
  );

  assert.match(markup, /<img[^>]*src="\/images\/paper-practice-empty-v1\.png"/);
  assert.match(markup, /<img[^>]*alt="Empty paper practice ledger"/);
  assert.match(markup, /<img[^>]*width="1536"[^>]*height="1024"/);
  assert.match(markup, /<img[^>]*sizes="\(min-width: 1024px\) 24rem, 100vw"/);
  assert.match(markup, /No paper order to review/);
  assert.match(markup, /Ask FinEd Saathi to prepare an NSE equity practice order/);
});

test('summary keeps final cash and historical cost values accessible during interpolation', () => {
  const { PortfolioSummary } = loadPortfolioSummary(React, (value) => value / 2);
  const markup = renderToStaticMarkup(
    React.createElement(PortfolioSummary, { portfolio: portfolio() })
  );

  includesAll(
    markup,
    [
      'aria-label="Virtual cash: ₹70,493.00"',
      'aria-label="Holdings historical cost basis: ₹29,507.00"',
      'aria-hidden="true">₹35,246.50',
      'aria-hidden="true">₹14,753.50',
      'Current/live value:',
      'trusted current quote is required',
    ],
    'missing accessible animated summary behavior'
  );
});

test('a provider-cleared fill draws one stroke-only confirmation and cancels it on cleanup', async () => {
  const pathNode = { style: {} };
  const hooks = statefulReact([pathNode]);
  const animations = [];
  const { OrderReview } = loadOrderReview(hooks.react, {
    reduceMotion: false,
    animate(target, options) {
      const animation = {
        cancelCalls: 0,
        cancel() {
          this.cancelCalls += 1;
        },
        options,
        target,
      };
      animations.push(animation);
      return animation;
    },
  });
  const clock = fakeBrowserClock(Date.parse('2026-08-08T09:31:00.000Z'));
  const props = {
    draft: draft(),
    portfolio: portfolio(),
    readiness: 'ready',
    onConfirm: async () => true,
  };

  try {
    let tree = hooks.render(OrderReview, props);
    const confirm = findElement(
      tree,
      (element) => element.type === 'button' && textContent(element) === 'Confirm paper buy'
    );
    await confirm.props.onClick();

    tree = hooks.renderBeforeEffects(OrderReview, { ...props, draft: null });
    assert.match(textContent(tree), /Paper order filled in your practice portfolio/);
    const confirmation = findElement(tree, (element) => element.type === 'svg');
    const confirmationPath = findElement(confirmation, (element) => element.type === 'path');
    assert.equal(confirmation?.props['aria-hidden'], 'true');
    assert.ok(confirmationPath, 'successful fill must render an SVG confirmation path');
    assert.equal(confirmationPath.props.pathLength, 1);
    assert.equal(confirmationPath.props.strokeDasharray, 1);
    assert.equal(confirmationPath.props.strokeDashoffset, 1);
    assert.equal(animations.length, 0, 'pre-effect render must already hide the path');

    hooks.flushEffects();
    assert.equal(animations.length, 1);
    assert.equal(animations[0].target, pathNode);
    assert.deepEqual(Object.keys(animations[0].options).sort(), [
      'duration',
      'ease',
      'strokeDashoffset',
    ]);
    assert.deepEqual(animations[0].options.strokeDashoffset, [1, 0]);

    hooks.strictModeReplayEffects();
    assert.equal(animations.length, 1, 'Strict Mode replay must not redraw the confirmation');
    assert.equal(animations[0].cancelCalls, 1);
    assert.equal(pathNode.style.strokeDashoffset, '0');
  } finally {
    hooks.unmount();
    clock.restore();
  }
});

test('reduced motion renders the successful confirmation in its final state', async () => {
  const pathNode = { style: {} };
  const hooks = statefulReact([pathNode]);
  let animateCalls = 0;
  const { OrderReview } = loadOrderReview(hooks.react, {
    reduceMotion: true,
    animate() {
      animateCalls += 1;
      return { cancel() {} };
    },
  });
  const clock = fakeBrowserClock(Date.parse('2026-08-08T09:31:00.000Z'));
  const props = {
    draft: draft(),
    portfolio: portfolio(),
    readiness: 'ready',
    onConfirm: async () => true,
  };

  try {
    let tree = hooks.render(OrderReview, props);
    const confirm = findElement(
      tree,
      (element) => element.type === 'button' && textContent(element) === 'Confirm paper buy'
    );
    await confirm.props.onClick();
    tree = hooks.renderBeforeEffects(OrderReview, props);

    const confirmationPath = findElement(tree, (element) => element.type === 'path');
    assert.ok(confirmationPath);
    assert.equal(confirmationPath.props.pathLength, 1);
    assert.equal(confirmationPath.props.strokeDasharray, 1);
    assert.equal(confirmationPath.props.strokeDashoffset, 0);
    assert.equal(animateCalls, 0);
    hooks.flushEffects();
    assert.equal(pathNode.style.strokeDashoffset, '0');
  } finally {
    hooks.unmount();
    clock.restore();
  }
});

test('renders browser-owned safeguards and wires enabled buy and sell confirmations', async () => {
  const dashboardMarkup = renderDashboard();
  includesAll(
    dashboardMarkup,
    [
      'Paper trading only',
      'No real money or broker account.',
      'Current/live value:',
      'trusted current quote is required',
      'This is a simulated paper order. No real money or broker order will be used.',
      'Simulated fills recorded in this browser.',
    ],
    'missing visible browser-owned paper safeguards'
  );

  for (const [side, cashEffectPaise, label] of [
    ['buy', -2_950_700, 'Confirm paper buy'],
    ['sell', 2_950_300, 'Confirm paper sell'],
  ]) {
    const hooks = statefulReact();
    const { OrderReview } = loadOrderReview(hooks.react);
    const clock = fakeBrowserClock(Date.parse('2026-08-08T09:31:00.000Z'));
    let confirmCalls = 0;
    try {
      const tree = hooks.render(OrderReview, {
        draft: draft({ side, cashEffectPaise }),
        portfolio: portfolio(),
        readiness: 'ready',
        async onConfirm() {
          confirmCalls += 1;
          return true;
        },
      });
      const confirm = findElement(
        tree,
        (element) => element.type === 'button' && textContent(element) === label
      );

      assert.ok(confirm, `${label} must render as a real button`);
      assert.equal(confirm.props.type, 'button');
      assert.notEqual(confirm.props.disabled, true);
      assert.equal(typeof confirm.props.onClick, 'function');
      await confirm.props.onClick();
      assert.equal(confirmCalls, 1);
    } finally {
      hooks.unmount();
      clock.restore();
    }
  }
});

test('renders an open ledger with native headings, status, tables, and mobile labels', () => {
  const markup = renderDashboard();

  includesAll(
    markup,
    [
      '<h1',
      '>Practice portfolio<',
      '<h2',
      '>Holdings<',
      '>Activity<',
      'role="status"',
      'aria-live="polite"',
      '<table',
      '<th scope="col">Instrument</th>',
      '<th scope="col">Historical cost basis</th>',
      '<dt>Current/live value</dt>',
      '<dt>Realized P&amp;L</dt>',
      'Unavailable',
      '−₹51.00',
    ],
    'missing semantic ledger behavior'
  );
  assert.ok(!markup.includes('overflow-x-auto'), 'paper ledger must not require horizontal scroll');
});

test('disables confirmation for expired, unavailable, and unaffordable paper buys', () => {
  const expired = renderDashboard({ draft: draft({ expiresAt: '2000-01-01T00:00:00.000Z' }) });
  assert.match(expired, /Paper quote expired/);
  assert.match(expired, /<button[^>]*disabled=""[^>]*>Confirm paper buy<\/button>/);

  const unavailable = renderDashboard({
    draft: draft({ chargePaise: null, cashEffectPaise: null, chargeStatus: 'unavailable' }),
  });
  assert.match(unavailable, /Estimated charges unavailable/);
  assert.match(unavailable, /<button[^>]*disabled=""[^>]*>Confirm paper buy<\/button>/);

  const insufficient = renderDashboard({
    portfolio: portfolio({ cashPaise: 100 }),
  });
  assert.match(insufficient, /Insufficient cash for paper buy/);
  assert.match(insufficient, /<button[^>]*disabled=""[^>]*>Confirm paper buy<\/button>/);
});

test('calculates an honest paper quote countdown at the exact expiry boundary', () => {
  const { paperQuoteExpiry } = loadOrderReview();

  assert.equal(typeof paperQuoteExpiry, 'function');
  assert.deepEqual(
    paperQuoteExpiry('2026-08-08T09:30:30.000Z', Date.parse('2026-08-08T09:30:00.001Z')),
    {
      expired: false,
      label: 'Expires in 00:30',
    }
  );
  assert.deepEqual(
    paperQuoteExpiry('2026-08-08T09:30:30.000Z', Date.parse('2026-08-08T09:30:29.999Z')),
    {
      expired: false,
      label: 'Expires in 00:01',
    }
  );
  assert.deepEqual(
    paperQuoteExpiry('2026-08-08T09:30:30.000Z', Date.parse('2026-08-08T09:30:30.000Z')),
    {
      expired: true,
      label: 'Expired',
    }
  );
});

test('schedules each countdown update at the next displayed-label boundary', () => {
  const hooks = statefulReact();
  const { OrderReview } = loadOrderReview(hooks.react);
  const clock = fakeBrowserClock(Date.parse('2026-08-08T09:30:00.000Z'));

  const props = {
    draft: draft({ expiresAt: '2026-08-08T09:30:02.500Z' }),
    portfolio: portfolio(),
    readiness: 'ready',
    onConfirm: async () => true,
  };

  try {
    let markup = renderToStaticMarkup(hooks.render(OrderReview, props));
    assert.match(markup, /Expires in 00:03/);
    assert.equal(clock.intervalCallCount(), 0);
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.nextTimeoutDelay(), 500);

    clock.runNextTimeout();
    markup = renderToStaticMarkup(hooks.render(OrderReview, props));
    assert.match(markup, /Expires in 00:02/);
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.nextTimeoutDelay(), 1_000);

    clock.runNextTimeout();
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.nextTimeoutDelay(), 1_000);

    clock.runNextTimeout();
    markup = renderToStaticMarkup(hooks.render(OrderReview, props));
    assert.match(markup, /Expired/);
    assert.match(markup, /<button[^>]*disabled=""[^>]*>Confirm paper buy<\/button>/);
    assert.equal(clock.activeTimerCount(), 0);
  } finally {
    hooks.unmount();
    clock.restore();
  }
});

test('suspends countdown scheduling while hidden and resumes from the wall clock', () => {
  const hooks = statefulReact();
  const { OrderReview } = loadOrderReview(hooks.react);
  const start = Date.parse('2026-08-08T09:30:00.000Z');
  const clock = fakeBrowserClock(start, true);
  const props = {
    draft: draft({ expiresAt: '2026-08-08T09:30:03.000Z' }),
    portfolio: portfolio(),
    readiness: 'ready',
    onConfirm: async () => true,
  };

  try {
    hooks.render(OrderReview, props);
    assert.equal(clock.activeTimerCount(), 0);
    assert.equal(clock.visibilityListenerCount(), 1);

    clock.setNow(start + 1_500);
    clock.setHidden(false);
    let markup = renderToStaticMarkup(hooks.render(OrderReview, props));
    assert.match(markup, /Expires in 00:02/);
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.nextTimeoutDelay(), 500);

    clock.setHidden(true);
    assert.equal(clock.activeTimerCount(), 0);
    clock.setNow(start + 3_500);
    clock.setHidden(false);
    markup = renderToStaticMarkup(hooks.render(OrderReview, props));
    assert.match(markup, /Expired/);
    assert.equal(clock.activeTimerCount(), 0);
  } finally {
    hooks.unmount();
    clock.restore();
  }
});

test('cleans and recreates one countdown scheduler across replacement, StrictMode, and unmount', () => {
  const hooks = statefulReact();
  const { OrderReview } = loadOrderReview(hooks.react);
  const clock = fakeBrowserClock(Date.parse('2026-08-08T09:30:00.000Z'));
  const props = {
    draft: draft({ expiresAt: '2026-08-08T09:30:03.000Z' }),
    portfolio: portfolio(),
    readiness: 'ready',
    onConfirm: async () => true,
  };

  try {
    hooks.render(OrderReview, props);
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.visibilityListenerCount(), 1);

    hooks.render(OrderReview, {
      ...props,
      draft: draft({ draftId: 'draft-2', expiresAt: '2026-08-08T09:30:05.000Z' }),
    });
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.visibilityListenerCount(), 1);

    hooks.strictModeReplayEffects();
    assert.equal(clock.activeTimerCount(), 1);
    assert.equal(clock.visibilityListenerCount(), 1);

    hooks.unmount();
    assert.equal(clock.activeTimerCount(), 0);
    assert.equal(clock.visibilityListenerCount(), 0);
  } finally {
    clock.restore();
  }
});

test('uses a real second reset confirmation and 44px controls', () => {
  const dashboard = read('components/paper-trading/paper-trading-dashboard.tsx');
  includesAll(
    dashboard,
    [
      'Settings',
      'role="dialog"',
      'aria-modal="true"',
      'Reset practice portfolio?',
      'Confirm reset practice',
      'resetPortfolio()',
      'min-h-11',
      'min-w-11',
    ],
    'missing reset or touch-target contract'
  );
});

test('keeps a rejected reset open with retry guidance inside the Radix dialog', async () => {
  let resetCalls = 0;
  const context = {
    view: 'dashboard',
    readiness: 'ready',
    portfolio: portfolio(),
    draft: null,
    error: null,
    openDashboard() {},
    closeDashboard() {},
    async confirmDraft() {
      return true;
    },
    async resetPortfolio() {
      resetCalls += 1;
      return false;
    },
  };
  const hooks = statefulReact();
  const Dashboard = loadDashboardForInteraction(hooks.react, context);
  let tree = hooks.render(Dashboard, {});
  let root = findElement(tree, (element) => element.type === Dialog.Root);

  assert.ok(root, 'reset must use the Radix dialog root');
  assert.equal(root.props.modal, true);
  assert.ok(findElement(root, (element) => element.type === Dialog.Trigger));
  root.props.onOpenChange(true);

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  let content = findElement(root, (element) => element.type === Dialog.Content);
  const confirm = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Confirm reset practice'
  );
  assert.ok(confirm, 'dialog must contain a separate reset confirmation');
  await confirm.props.onClick();

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  content = findElement(root, (element) => element.type === Dialog.Content);
  const alert = findElement(content, (element) => element.props?.role === 'alert');
  assert.equal(root.props.open, true, 'failed reset must keep the dialog open');
  assert.equal(resetCalls, 1);
  assert.ok(alert, 'failed reset guidance must be inside Dialog.Content');
  assert.match(textContent(alert), /could not be reset.*Try again/i);
  const retry = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Confirm reset practice'
  );
  assert.notEqual(retry?.props.disabled, true, 'failed reset must leave retry focusable');
  assert.notEqual(retry?.props['aria-disabled'], true, 'failed reset must leave retry enabled');
});

test('fails closed when reset persistence makes browser storage unavailable', async () => {
  let resetCalls = 0;
  const context = {
    view: 'dashboard',
    readiness: 'ready',
    portfolio: portfolio(),
    draft: null,
    error: null,
    openDashboard() {},
    closeDashboard() {},
    async confirmDraft() {
      return true;
    },
    async resetPortfolio() {
      resetCalls += 1;
      context.readiness = 'unavailable';
      return false;
    },
  };
  const hooks = statefulReact();
  const Dashboard = loadDashboardForInteraction(hooks.react, context);
  let tree = hooks.render(Dashboard, {});
  let root = findElement(tree, (element) => element.type === Dialog.Root);
  root.props.onOpenChange(true);

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  let content = findElement(root, (element) => element.type === Dialog.Content);
  let confirm = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Confirm reset practice'
  );
  await confirm.props.onClick();

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  content = findElement(root, (element) => element.type === Dialog.Content);
  const alert = findElement(content, (element) => element.props?.role === 'alert');
  confirm = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Confirm reset practice'
  );

  assert.equal(root.props.open, true, 'unavailable storage must leave recovery guidance visible');
  assert.equal(resetCalls, 1);
  assert.ok(alert, 'storage recovery guidance must be inside Dialog.Content');
  assert.match(textContent(alert), /browser storage is unavailable/i);
  assert.match(textContent(alert), /close.*restore site storage access.*reload/i);
  assert.doesNotMatch(textContent(alert), /try again/i);
  assert.equal(confirm?.props['aria-disabled'], true, 'reset must be visibly unavailable');

  await confirm.props.onClick();
  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  content = findElement(root, (element) => element.type === Dialog.Content);
  assert.equal(resetCalls, 1, 'an unavailable provider must not be called again');
  assert.match(
    textContent(findElement(content, (element) => element.props?.role === 'alert')),
    /browser storage is unavailable/i
  );
});

test('blocks every Radix dismissal path while reset persistence is pending', async () => {
  let settleReset;
  let resetCalls = 0;
  const context = {
    view: 'dashboard',
    readiness: 'ready',
    portfolio: portfolio(),
    draft: null,
    error: null,
    openDashboard() {},
    closeDashboard() {},
    async confirmDraft() {
      return true;
    },
    resetPortfolio() {
      resetCalls += 1;
      return new Promise((resolve) => {
        settleReset = resolve;
      });
    },
  };
  const hooks = statefulReact();
  const Dashboard = loadDashboardForInteraction(hooks.react, context);
  let tree = hooks.render(Dashboard, {});
  let root = findElement(tree, (element) => element.type === Dialog.Root);
  root.props.onOpenChange(true);

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  let content = findElement(root, (element) => element.type === Dialog.Content);
  let confirm = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Confirm reset practice'
  );
  const pendingReset = confirm.props.onClick();

  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  content = findElement(root, (element) => element.type === Dialog.Content);
  root.props.onOpenChange(false);
  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  content = findElement(root, (element) => element.type === Dialog.Content);
  assert.equal(root.props.open, true, 'controlled close must be ignored while pending');

  for (const eventName of ['onEscapeKeyDown', 'onPointerDownOutside', 'onInteractOutside']) {
    let prevented = false;
    assert.equal(typeof content.props[eventName], 'function', `${eventName} guard is required`);
    content.props[eventName]({
      preventDefault() {
        prevented = true;
      },
    });
    assert.equal(prevented, true, `${eventName} must be prevented while pending`);
  }

  const close = findElement(
    content,
    (element) =>
      element.type === 'button' && element.props['aria-label'] === 'Close reset confirmation'
  );
  const cancel = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Keep practice portfolio'
  );
  confirm = findElement(
    content,
    (element) => element.type === 'button' && textContent(element) === 'Resetting practice'
  );
  assert.equal(close?.props.disabled, true);
  assert.equal(cancel?.props.disabled, true);
  assert.notEqual(confirm?.props.disabled, true, 'pending confirm must remain focusable');
  assert.equal(confirm?.props['aria-disabled'], true);
  await confirm.props.onClick();
  assert.equal(resetCalls, 1, 'pending confirm must reject repeat activation');

  settleReset(true);
  await pendingReset;
  tree = hooks.render(Dashboard, {});
  root = findElement(tree, (element) => element.type === Dialog.Root);
  const trigger = findElement(
    root,
    (element) => element.type === 'button' && textContent(element) === 'Reset practice'
  );
  assert.equal(root.props.open, false);
  assert.equal(
    trigger?.props.disabled,
    false,
    'successful close must restore to an enabled trigger'
  );
});

test('puts order review before holdings in the mobile reading order', () => {
  const dashboard = read('components/paper-trading/paper-trading-dashboard.tsx');

  assert.ok(
    dashboard.indexOf('<OrderReview') < dashboard.indexOf('<HoldingsLedger'),
    'mobile DOM order must put order review before holdings'
  );
});

test('focuses the dashboard heading after the paper workspace renders', () => {
  let focusCalls = 0;
  const hooks = statefulReact([
    {
      focus() {
        focusCalls += 1;
      },
    },
  ]);
  const context = {
    view: 'dashboard',
    readiness: 'ready',
    portfolio: portfolio(),
    draft: null,
    error: null,
    openDashboard() {},
    closeDashboard() {},
    async confirmDraft() {
      return true;
    },
    async resetPortfolio() {
      return true;
    },
  };
  const Dashboard = loadDashboardForInteraction(hooks.react, context);
  const tree = hooks.render(Dashboard, {});
  const heading = findElement(tree, (element) => element.type === 'h1');

  assert.equal(heading?.props.tabIndex, -1);
  assert.equal(focusCalls, 1);
});

test('restores focus to the Paper trading trigger after returning to learning', () => {
  let focusCalls = 0;
  const trigger = {
    focus() {
      focusCalls += 1;
    },
  };
  const hooks = statefulReact([trigger]);
  const paperTrading = {
    view: 'dashboard',
    openDashboard() {},
    closeDashboard() {},
  };
  const SessionView = loadSessionViewForFocus(hooks.react, paperTrading);

  hooks.render(SessionView, { appConfig: {}, learningMode: 'general' });
  assert.equal(focusCalls, 0);
  paperTrading.view = 'session';
  hooks.render(SessionView, { appConfig: {}, learningMode: 'general' });
  assert.equal(focusCalls, 1);
});
