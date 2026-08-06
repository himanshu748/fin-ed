import * as React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as jsxRuntime from 'react/jsx-runtime';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const frontendRoot = join(import.meta.dirname, '..');
const repoRoot = join(frontendRoot, '..');

function read(relativePath) {
  return readFileSync(join(frontendRoot, relativePath), 'utf8');
}

function readRepo(relativePath) {
  return readFileSync(join(repoRoot, relativePath), 'utf8');
}

function includesAll(source, values, message) {
  for (const value of values) {
    assert.ok(source.includes(value), `${message}: ${value}`);
  }
}

function loadReveal({ react = React, useReducedMotion = () => false } = {}) {
  const output = ts.transpileModule(read('components/app/reveal.tsx'), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const compiledModule = { exports: {} };
  const dependencies = new Map([
    ['react', react],
    ['react/jsx-runtime', jsxRuntime],
    ['motion/react', { useReducedMotion }],
    ['@/lib/shadcn/utils', { cn: (...values) => values.filter(Boolean).join(' ') }],
  ]);

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected Reveal dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );

  return compiledModule.exports.Reveal;
}

test('publishes the FinEd Saathi identity, viewport, and Ledger typography', () => {
  const config = read('app-config.ts');
  const layout = read('app/layout.tsx');
  const styles = read('styles/globals.css');

  includesAll(config, ['FinEd Saathi', 'Indian market'], 'missing FinEd identity');
  includesAll(
    layout,
    [
      "width: 'device-width'",
      'initialScale: 1',
      'lang="en-IN"',
      "locale: 'en_IN'",
      'preconnect',
      'fonts.googleapis.com',
      'fonts.gstatic.com',
    ],
    'missing viewport or font setup'
  );
  includesAll(layout, ['Manrope', 'Source_Sans_3', 'IBM_Plex_Mono'], 'missing font family');
  includesAll(
    styles.toUpperCase(),
    ['#F6F2E8', '#FFFCF5', '#15233B', '#174EA6', '#1F6B4F', '#A13D35'],
    'missing Ledger palette'
  );
});

test('renders the complete Day 1 landing narrative and safety boundary', () => {
  const welcome = read('components/app/welcome-view.tsx');

  includesAll(
    welcome,
    [
      'VOICE-FIRST FINANCIAL LITERACY FOR INDIA',
      'Price same tha. Phir loss kahan se hua?',
      'Talk to FinEd Saathi',
      'See the ₹6 breakdown',
      'Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP.',
      'How it works',
      'Price loss zero tha. Cost loss zero nahi tha.',
      'Sunega bhi. Samjhayega bhi.',
      'Broker ka answer akela final answer nahi hai.',
      'Agla trade nahi. Agla concept samjho.',
    ],
    'missing required landing copy'
  );
});

test('uses an accessible inline receipt illustration with the ₹6 example', () => {
  const receipt = read('components/app/fee-receipt.tsx');

  includesAll(
    receipt,
    [
      '<svg',
      '<title',
      '<desc',
      'sixRupeeFixture',
      'NSE delivery illustration',
      'assumptions.buy_price',
      'assumptions.sell_price',
      'Price P&amp;L ₹0.00',
      'result.total_charges',
      'Net about negative',
      '₹50',
    ],
    'missing receipt contract'
  );
});

test('offers semantic learning modes from the shared mode catalog', () => {
  const modes = read('components/app/mode-bento.tsx');

  includesAll(
    modes,
    [
      'LEARNING_MODES',
      'role="radiogroup"',
      'role="radio"',
      'aria-checked',
      'F&O can create rapid and substantial losses. This mode teaches mechanics and risk only. It does not provide calls or strategies for a live trade.',
    ],
    'missing learning mode contract'
  );
});

test('keeps the connected experience educational, transparent, and single-disconnect', () => {
  const session = read('components/app/fin-ed-session-view.tsx');
  const transcript = read('components/agents-ui/agent-chat-transcript.tsx');
  const controls = read('components/agents-ui/agent-control-bar.tsx');

  includesAll(
    session,
    ['Mode locked for this call', 'Education only.', 'AgentAudioVisualizerBar'],
    'missing session guardrails'
  );
  assert.ok(
    !session.includes('onDisconnect='),
    'session must not layer a second disconnect callback'
  );
  includesAll(
    transcript,
    [
      "const locale = 'en-IN'",
      'Ask your first market question',
      'Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua.',
    ],
    'missing connected empty state'
  );
  includesAll(
    controls,
    ['Type a market question', '<label', 'htmlFor='],
    'missing semantic market question input'
  );
  assert.ok(!controls.includes('autoFocus'), 'chat input must not steal focus');
});

test('honors reduced motion without idle animation loops', () => {
  const styles = read('styles/globals.css');
  const reveal = read('components/app/reveal.tsx');
  const conversation = read('components/ai-elements/conversation.tsx');
  const visualizer = read('hooks/agents-ui/use-agent-audio-visualizer-bar.ts');

  includesAll(
    styles,
    ['prefers-reduced-motion', ':focus-visible'],
    'missing global motion or focus handling'
  );
  includesAll(reveal, ['useReducedMotion'], 'reveal must respect reduced motion');
  includesAll(
    conversation,
    ['prefers-reduced-motion', 'instant'],
    'conversation must avoid smooth motion'
  );
  assert.ok(
    !visualizer.includes('requestAnimationFrame'),
    'idle visualizer must not run an animation frame loop'
  );
  includesAll(visualizer, ['prefers-reduced-motion', 'speaking'], 'visualizer must gate motion');
});

test('does not leak starter branding, pill actions, or prohibited punctuation', () => {
  const visibleFiles = [
    'app-config.ts',
    'app/layout.tsx',
    'app/opengraph-image.tsx',
    'components/app/site-nav.tsx',
    'components/app/fee-receipt.tsx',
    'components/app/mode-bento.tsx',
    'components/app/welcome-view.tsx',
    'components/app/fin-ed-session-view.tsx',
  ];
  const sources = visibleFiles.map((file) => [file, read(file)]);

  for (const [file, source] of sources) {
    assert.ok(!source.includes('Voice AI Starter'), `${file} contains starter branding`);
    assert.ok(
      !source.includes('Chat live with your voice AI agent'),
      `${file} contains starter copy`
    );
    assert.ok(!/[—–]/u.test(source), `${file} contains a Unicode dash`);
  }

  for (const file of [
    'components/app/site-nav.tsx',
    'components/app/mode-bento.tsx',
    'components/app/welcome-view.tsx',
    'components/app/fin-ed-session-view.tsx',
  ]) {
    assert.ok(!read(file).includes('rounded-full'), `${file} contains a pill action`);
  }
});

test('keeps the ₹6 illustration auditable and the remembered ₹50 unresolved', () => {
  const fixture = JSON.parse(read('data/six-rupee-delivery.json'));
  const receipt = read('components/app/fee-receipt.tsx');
  const welcome = read('components/app/welcome-view.tsx');

  assert.deepEqual(fixture.assumptions, {
    broker: 'Angel One',
    trade_date: '2026-08-06',
    product: 'equity_delivery',
    exchange: 'NSE',
    quantity: 1,
    buy_price: '6.00',
    sell_price: '6.00',
    executed_buy_orders: 1,
    executed_sell_orders: 1,
    demat_debits: 1,
    brokerage_promotion_applies: false,
  });
  assert.equal(
    fixture.rules.brokerage,
    'lower of ₹20 or 0.1% per executed order, subject to a ₹5 minimum'
  );
  assert.equal(fixture.rules.dp_charge, '₹20 before GST per ISIN per sell-side demat debit');
  assert.deepEqual(fixture.result, {
    brokerage_buy: '5.00',
    brokerage_sell: '5.00',
    dp_charge_before_gst: '20.00',
    total_charges: '35.41',
    net_pnl: '-35.41',
    fee_to_investment_percent: '590.22',
    break_even_sell_price: '41.46',
  });
  assert.equal(fixture.historical_loss_status, 'unresolved');

  includesAll(
    `${receipt}\n${welcome}`,
    [
      'sixRupeeFixture',
      'executed_buy_orders',
      'executed_sell_orders',
      'demat_debits',
      'brokerage_buy',
      'brokerage_sell',
      'fee_to_investment_percent',
      'break_even_sell_price',
      'Contract-note or Trades & Charges rows outrank this generic estimate.',
      'contract-note total charges, ledger or available funds, or P&L',
    ],
    'missing auditable reconciliation data'
  );
  for (const field of [
    'sixRupeeRules.brokerage',
    'sixRupeeAssumptions.executed_buy_orders',
    'sixRupeeAssumptions.executed_sell_orders',
    'sixRupeeAssumptions.demat_debits',
  ]) {
    assert.ok(
      (welcome.match(new RegExp(field.replace('.', '\\.'), 'g')) ?? []).length >= 3,
      `${field} must appear in the breakdown, FAQ, and transcript`
    );
  }
  assert.ok(!welcome.includes('590.17%'), 'UI contains the stale displayed-total ratio');
});

test('labels both SEBI sources truthfully in the UI and packaged schedule', () => {
  const welcome = read('components/app/welcome-view.tsx');
  const schedule = JSON.parse(readRepo('backend/src/fined/data/angel_one_schedules.json'))
    .schedules[0];
  const sourceByUrl = new Map(schedule.sources.map((source) => [source.url, source.title]));
  const stampUrl = 'https://www.sebi.gov.in/sebi_data/faqfiles/sep-2020/1599820228476.pdf';
  const turnoverUrl = 'https://www.sebi.gov.in/sebi_data/commondocs/stockbroamendregu_p.pdf';

  assert.equal(sourceByUrl.get(stampUrl), 'SEBI FAQ on Indian Stamp Act amendments');
  assert.equal(sourceByUrl.get(turnoverUrl), 'SEBI Stock Brokers Regulations, Schedule V');
  includesAll(
    welcome,
    [
      'SEBI FAQ on Indian Stamp Act amendments',
      stampUrl,
      'SEBI Stock Brokers Regulations, Schedule V',
      turnoverUrl,
    ],
    'missing truthful SEBI source identity'
  );
  assert.ok(
    !welcome.includes('Turnover fee FAQ'),
    'stamp-duty PDF is mislabeled as turnover proof'
  );
});

test('server-rendered Reveal emits visible content before hydration', () => {
  const Reveal = loadReveal();
  const markup = renderToStaticMarkup(
    React.createElement(Reveal, { className: 'visible-shell' }, 'Visible content')
  );

  assert.match(markup, /^<div class="visible-shell">Visible content<\/div>$/);
  assert.doesNotMatch(markup, /\sstyle=/i);
  assert.doesNotMatch(markup, /\shidden(?:=|\s|>)/i);
  assert.doesNotMatch(markup, /(?:opacity-0|translate-[xy]|translate\(|translate[XY]\()/i);
});

test('reduced-motion Reveal does not observe or animate the element', () => {
  let observerConstructions = 0;
  let observeCalls = 0;
  let animateCalls = 0;
  const cleanups = [];
  const node = {
    animate() {
      animateCalls += 1;
      return { cancel() {} };
    },
  };
  const react = {
    useEffect(effect) {
      const cleanup = effect();
      if (cleanup) cleanups.push(cleanup);
    },
    useRef() {
      return { current: node };
    },
  };
  const previousObserver = globalThis.IntersectionObserver;

  globalThis.IntersectionObserver = class MockIntersectionObserver {
    constructor(callback) {
      observerConstructions += 1;
      this.callback = callback;
    }

    observe() {
      observeCalls += 1;
      this.callback([{ isIntersecting: true }]);
    }

    disconnect() {}
  };

  try {
    const Reveal = loadReveal({ react, useReducedMotion: () => true });
    Reveal({ children: 'Visible content' });
    for (const cleanup of cleanups) cleanup();
  } finally {
    if (previousObserver === undefined) delete globalThis.IntersectionObserver;
    else globalThis.IntersectionObserver = previousObserver;
  }

  assert.deepEqual(
    { observerConstructions, observeCalls, animateCalls },
    { observerConstructions: 0, observeCalls: 0, animateCalls: 0 }
  );
});
