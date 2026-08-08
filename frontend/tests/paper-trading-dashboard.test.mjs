import * as React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as jsxRuntime from 'react/jsx-runtime';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

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
  ]);
  const portfolioSummary = compile('components/paper-trading/portfolio-summary.tsx', common);
  common.set('@/components/paper-trading/portfolio-summary', portfolioSummary);
  const holdingsLedger = compile('components/paper-trading/holdings-ledger.tsx', common);
  const activityLedger = compile('components/paper-trading/activity-ledger.tsx', common);
  const orderReview = compile('components/paper-trading/order-review.tsx', common);
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

test('puts order review before holdings in the mobile reading order', () => {
  const dashboard = read('components/paper-trading/paper-trading-dashboard.tsx');

  assert.ok(
    dashboard.indexOf('<OrderReview') < dashboard.indexOf('<HoldingsLedger'),
    'mobile DOM order must put order review before holdings'
  );
});
