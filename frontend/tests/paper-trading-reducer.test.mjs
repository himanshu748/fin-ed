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

const { decodePaperOrderDraft } = require('../lib/paper-trading/schema.ts');
const { createPaperPortfolio, reducePaperPortfolio } = require('../lib/paper-trading/reducer.ts');

const NOW = '2026-08-08T00:00:00.000Z';

function draftFixture(changes = {}) {
  return {
    version: 1,
    paper: true,
    draft_id: 'draft-1',
    side: 'buy',
    exchange: 'NSE',
    symbol_token: '2885',
    trading_symbol: 'RELIANCE-EQ',
    quantity: 2,
    price_paise: 250_000,
    quote_provider: 'Angel One SmartAPI',
    quote_time: '2026-08-08T00:00:00.000Z',
    expires_at: '2026-08-08T00:00:30.000Z',
    notional_paise: 500_000,
    charge_paise: 100,
    cash_effect_paise: -500_100,
    charge_status: 'estimated',
    ...changes,
  };
}

function draft(changes = {}) {
  const raw = draftFixture(changes);
  if (changes.quantity !== undefined || changes.price_paise !== undefined) {
    raw.notional_paise = raw.quantity * raw.price_paise;
  }
  if (
    changes.side === 'sell' ||
    changes.charge_paise !== undefined ||
    changes.quantity !== undefined ||
    changes.price_paise !== undefined
  ) {
    raw.cash_effect_paise =
      raw.side === 'buy'
        ? -(raw.notional_paise + raw.charge_paise)
        : raw.notional_paise - raw.charge_paise;
  }
  return decodePaperOrderDraft(raw);
}

function confirm(state, order, now = NOW) {
  return reducePaperPortfolio(state, { type: 'confirmDraft', draft: order, now });
}

test('starts with exactly one lakh rupees', () => {
  const state = createPaperPortfolio(NOW, 'portfolio-1');

  assert.equal(state.startingCashPaise, 10_000_000);
  assert.equal(state.cashPaise, 10_000_000);
  assert.equal(state.revision, 0);
  assert.deepEqual(state.holdings, []);
});

test('accepts backend-shaped microsecond timestamps with offsets', () => {
  const timestamp = '2026-08-08T05:30:00.123456+05:30';
  const order = draft({
    quote_time: timestamp,
    expires_at: '2026-08-08T05:30:30.123456+05:30',
  });

  const next = confirm(createPaperPortfolio(timestamp, 'portfolio-1'), order, timestamp);

  assert.equal(next.cashPaise, 9_499_900);
  assert.equal(next.fills[0].filledAt, timestamp);
  assert.throws(
    () =>
      draft({
        quote_time: timestamp,
        expires_at: '2026-08-08T05:30:30.123457+05:30',
      }),
    /expiry/
  );
});

test('rejects impossible calendar dates in drafts and reducer actions', () => {
  assert.throws(
    () =>
      draft({
        quote_time: '2026-02-30T05:30:00.123456+05:30',
        expires_at: '2026-02-30T05:30:30.123456+05:30',
      }),
    /timestamp/
  );
  assert.throws(() => createPaperPortfolio('2026-02-30T00:00:00.000Z', 'portfolio-1'), /timestamp/);
});

test('records a confirmed paper buy once without mutating the prior portfolio', () => {
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const order = draft();
  const next = confirm(initial, order);

  assert.equal(next.cashPaise, 9_499_900);
  assert.deepEqual(next.holdings, [
    {
      exchange: 'NSE',
      symbolToken: '2885',
      tradingSymbol: 'RELIANCE-EQ',
      quantity: 2,
      costBasisPaise: 500_100,
      averageCostPaise: 250_050,
    },
  ]);
  assert.equal(next.appliedDraftIds.includes(order.draftId), true);
  assert.equal(next.revision, 1);
  assert.equal(initial.cashPaise, 10_000_000);
  assert.deepEqual(initial.holdings, []);
  assert.throws(() => confirm(next, order), /already applied/);
});

test('uses weighted average cost across paper buys', () => {
  const initial = confirm(createPaperPortfolio(NOW, 'portfolio-1'), draft());
  const second = draft({
    draft_id: 'draft-2',
    quantity: 1,
    price_paise: 300_000,
    charge_paise: 0,
  });
  const next = confirm(initial, second, '2026-08-08T00:00:01.000Z');

  assert.deepEqual(next.holdings[0], {
    exchange: 'NSE',
    symbolToken: '2885',
    tradingSymbol: 'RELIANCE-EQ',
    quantity: 3,
    costBasisPaise: 800_100,
    averageCostPaise: 266_700,
  });
  assert.equal(next.cashPaise, 9_199_900);
});

test('records partial and full sells with realized P&L and charges', () => {
  const bought = confirm(createPaperPortfolio(NOW, 'portfolio-1'), draft());
  const partialSell = draft({
    draft_id: 'draft-2',
    side: 'sell',
    quantity: 1,
    price_paise: 300_000,
    charge_paise: 100,
  });
  const afterPartial = confirm(bought, partialSell, '2026-08-08T00:00:01.000Z');

  assert.equal(afterPartial.cashPaise, 9_799_800);
  assert.deepEqual(afterPartial.holdings[0], {
    exchange: 'NSE',
    symbolToken: '2885',
    tradingSymbol: 'RELIANCE-EQ',
    quantity: 1,
    costBasisPaise: 250_050,
    averageCostPaise: 250_050,
  });
  assert.equal(afterPartial.fills.at(-1).realizedPnlPaise, 49_850);

  const fullSell = draft({
    draft_id: 'draft-3',
    side: 'sell',
    quantity: 1,
    price_paise: 200_000,
    charge_paise: 50,
  });
  const afterFull = confirm(afterPartial, fullSell, '2026-08-08T00:00:02.000Z');

  assert.deepEqual(afterFull.holdings, []);
  assert.equal(afterFull.cashPaise, 9_999_750);
  assert.equal(afterFull.fills.at(-1).realizedPnlPaise, -50_100);
});

test('rejects a buy without enough cash and a sell without enough holdings', () => {
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const unaffordable = draft({
    draft_id: 'expensive',
    quantity: 100,
    price_paise: 200_000,
    charge_paise: 0,
  });
  assert.throws(() => confirm(initial, unaffordable), /Insufficient cash/);

  const unsupportedShort = draft({
    draft_id: 'sell-unknown',
    side: 'sell',
    quantity: 1,
    charge_paise: 0,
  });
  assert.throws(() => confirm(initial, unsupportedShort), /Insufficient holdings/);
});

test('rejects expired, unknown, and non-NSE drafts before changing the portfolio', () => {
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const expired = draft({
    draft_id: 'expired',
    quote_time: '2026-08-07T23:59:00.000Z',
    expires_at: '2026-08-07T23:59:30.000Z',
  });
  assert.throws(() => confirm(initial, expired), /expired/);
  assert.throws(
    () =>
      reducePaperPortfolio(initial, {
        type: 'confirmDraft',
        draft: { draftId: 'unknown' },
        now: NOW,
      }),
    /Unknown paper draft/
  );
  assert.throws(() => confirm(initial, draft({ draft_id: 'bse', exchange: 'BSE' })), /NSE/);
  assert.equal(initial.revision, 0);
});

test('rejects unsafe paise arithmetic and invalid reset actions', () => {
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  assert.throws(
    () =>
      draft({
        draft_id: 'overflow',
        quantity: Number.MAX_SAFE_INTEGER,
        price_paise: 2,
        charge_paise: 0,
      }),
    /safe integer/
  );
  const unsafeHolding = {
    ...initial,
    holdings: [
      {
        exchange: 'NSE',
        symbolToken: '2885',
        tradingSymbol: 'RELIANCE-EQ',
        quantity: Number.MAX_SAFE_INTEGER,
        costBasisPaise: Number.MAX_SAFE_INTEGER,
        averageCostPaise: 1,
      },
    ],
  };
  assert.throws(
    () => reducePaperPortfolio(unsafeHolding, { type: 'reset', now: NOW }),
    /safe integer/
  );
  assert.throws(() => reducePaperPortfolio(initial, { type: 'reset', now: 'nope' }), /timestamp/);
});

test('increments revision and resets to the original virtual cash balance', () => {
  const bought = confirm(createPaperPortfolio(NOW, 'portfolio-1'), draft());
  const reset = reducePaperPortfolio(bought, {
    type: 'reset',
    now: '2026-08-08T00:02:00.000Z',
  });

  assert.equal(reset.revision, 2);
  assert.equal(reset.cashPaise, 10_000_000);
  assert.deepEqual(reset.holdings, []);
  assert.deepEqual(reset.fills, []);
  assert.deepEqual(reset.appliedDraftIds, []);
  assert.equal(reset.portfolioId, bought.portfolioId);
});
