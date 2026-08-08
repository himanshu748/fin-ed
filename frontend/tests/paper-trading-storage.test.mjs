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

const { createPaperPortfolio, reducePaperPortfolio } = require('../lib/paper-trading/reducer.ts');
const {
  PAPER_PORTFOLIO_STORAGE_KEY,
  loadPaperPortfolio,
  savePaperPortfolio,
} = require('../lib/paper-trading/storage.ts');
const { decodePaperOrderDraft } = require('../lib/paper-trading/schema.ts');

const NOW = '2026-08-08T00:00:00.000Z';

function memoryStorage(entries = {}) {
  const values = new Map(Object.entries(entries));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

function exclusiveLockCoordinator() {
  let tail = Promise.resolve();
  let requestCount = 0;
  return {
    get requestCount() {
      return requestCount;
    },
    request(name, options, callback) {
      assert.equal(name, PAPER_PORTFOLIO_STORAGE_KEY);
      assert.deepEqual(options, { mode: 'exclusive' });
      requestCount += 1;
      const result = tail.then(callback);
      tail = result.then(
        () => undefined,
        () => undefined
      );
      return result;
    },
  };
}

function buyDraft() {
  return decodePaperOrderDraft({
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
    quote_time: NOW,
    expires_at: '2026-08-08T00:00:30.000Z',
    notional_paise: 250_000,
    charge_paise: 0,
    cash_effect_paise: -250_000,
    charge_status: 'estimated',
  });
}

function sellDraft() {
  return decodePaperOrderDraft({
    version: 1,
    paper: true,
    draft_id: 'draft-2',
    side: 'sell',
    exchange: 'NSE',
    symbol_token: '2885',
    trading_symbol: 'RELIANCE-EQ',
    quantity: 1,
    price_paise: 300_000,
    quote_provider: 'Angel One SmartAPI',
    quote_time: '2026-08-08T00:00:01.000Z',
    expires_at: '2026-08-08T00:00:31.000Z',
    notional_paise: 300_000,
    charge_paise: 100,
    cash_effect_paise: 299_900,
    charge_status: 'estimated',
  });
}

test('reports a missing browser portfolio without creating one', () => {
  const storage = memoryStorage();

  assert.deepEqual(loadPaperPortfolio(storage), { status: 'missing' });
});

test('persists and strictly reloads a valid version-one portfolio', async () => {
  const storage = memoryStorage();
  const portfolio = createPaperPortfolio(NOW, 'portfolio-1');
  const locks = exclusiveLockCoordinator();

  assert.deepEqual(await savePaperPortfolio(storage, portfolio, locks), {
    status: 'saved',
    portfolio,
  });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'ready', portfolio });
});

test('reports corrupt JSON and unknown schema data without accepting either', () => {
  const corrupt = memoryStorage({ [PAPER_PORTFOLIO_STORAGE_KEY]: '{' });
  assert.deepEqual(loadPaperPortfolio(corrupt), { status: 'corrupt', raw: '{' });

  const unknown = memoryStorage({
    [PAPER_PORTFOLIO_STORAGE_KEY]: JSON.stringify({ schemaVersion: 2 }),
  });
  assert.deepEqual(loadPaperPortfolio(unknown), {
    status: 'corrupt',
    raw: JSON.stringify({ schemaVersion: 2 }),
  });
});

test('rejects structurally valid portfolios whose fills cannot replay', () => {
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const bought = reducePaperPortfolio(initial, {
    type: 'confirmDraft',
    draft: buyDraft(),
    now: NOW,
  });
  const sold = reducePaperPortfolio(bought, {
    type: 'confirmDraft',
    draft: sellDraft(),
    now: '2026-08-08T00:00:01.000Z',
  });
  const sellWithoutBuy = {
    ...sold,
    cashPaise: 10_299_900,
    holdings: [],
    fills: [sold.fills[1]],
    appliedDraftIds: ['draft-2'],
  };
  const impossiblePortfolios = [
    { ...sold, cashPaise: sold.cashPaise + 1 },
    { ...sold, holdings: [bought.holdings[0]] },
    { ...sold, appliedDraftIds: ['draft-2', 'draft-1'] },
    sellWithoutBuy,
    {
      ...sold,
      fills: sold.fills.map((fill, index) =>
        index === 1 ? { ...fill, realizedPnlPaise: fill.realizedPnlPaise + 1 } : fill
      ),
    },
  ];

  for (const portfolio of impossiblePortfolios) {
    assert.deepEqual(
      loadPaperPortfolio(
        memoryStorage({ [PAPER_PORTFOLIO_STORAGE_KEY]: JSON.stringify(portfolio) })
      ),
      { status: 'corrupt', raw: JSON.stringify(portfolio) }
    );
  }
});

test('reports unavailable storage when browser access throws', async () => {
  const unavailable = {
    getItem() {
      throw new Error('blocked');
    },
    setItem() {
      throw new Error('blocked');
    },
  };

  assert.deepEqual(loadPaperPortfolio(unavailable), { status: 'unavailable' });
  assert.deepEqual(
    await savePaperPortfolio(
      unavailable,
      createPaperPortfolio(NOW, 'portfolio-1'),
      exclusiveLockCoordinator()
    ),
    { status: 'unavailable' }
  );
});

test('keeps the newer revision already written by another tab', async () => {
  const storage = memoryStorage();
  const older = createPaperPortfolio(NOW, 'portfolio-1');
  const newer = reducePaperPortfolio(older, { type: 'reset', now: '2026-08-08T00:01:00.000Z' });
  const locks = exclusiveLockCoordinator();

  assert.equal((await savePaperPortfolio(storage, newer, locks)).status, 'saved');
  assert.deepEqual(await savePaperPortfolio(storage, older, locks), {
    status: 'stale',
    portfolio: newer,
  });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'ready', portfolio: newer });
});

test('rejects divergent equal-revision portfolios from another tab', async () => {
  const storage = memoryStorage();
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const existing = reducePaperPortfolio(initial, {
    type: 'reset',
    now: '2026-08-08T00:00:01.000Z',
  });
  const divergent = reducePaperPortfolio(initial, {
    type: 'confirmDraft',
    draft: buyDraft(),
    now: '2026-08-08T00:00:02.000Z',
  });
  const locks = exclusiveLockCoordinator();

  assert.equal(existing.revision, divergent.revision);
  assert.notDeepEqual(existing, divergent);
  assert.equal((await savePaperPortfolio(storage, existing, locks)).status, 'saved');
  assert.deepEqual(await savePaperPortfolio(storage, divergent, locks), {
    status: 'stale',
    portfolio: existing,
  });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'ready', portfolio: existing });
});

test('does not claim a safe save when cross-tab coordination is unavailable', async () => {
  const storage = memoryStorage();
  const portfolio = createPaperPortfolio(NOW, 'portfolio-1');

  assert.deepEqual(await savePaperPortfolio(storage, portfolio, null), { status: 'unavailable' });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'missing' });
});

test('serializes concurrent divergent revision-one saves through one exclusive lock', async () => {
  const storage = memoryStorage();
  const initial = createPaperPortfolio(NOW, 'portfolio-1');
  const firstCandidate = reducePaperPortfolio(initial, {
    type: 'reset',
    now: '2026-08-08T00:00:01.000Z',
  });
  const secondCandidate = reducePaperPortfolio(initial, {
    type: 'confirmDraft',
    draft: buyDraft(),
    now: '2026-08-08T00:00:02.000Z',
  });
  const locks = exclusiveLockCoordinator();

  const first = savePaperPortfolio(storage, firstCandidate, locks);
  const second = savePaperPortfolio(storage, secondCandidate, locks);
  const [firstResult, secondResult] = await Promise.all([first, second]);

  assert.equal(locks.requestCount, 2);
  assert.equal([firstResult, secondResult].filter((result) => result.status === 'saved').length, 1);
  assert.deepEqual(firstResult, { status: 'saved', portfolio: firstCandidate });
  assert.deepEqual(secondResult, { status: 'stale', portfolio: firstCandidate });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'ready', portfolio: firstCandidate });
});
