import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  module._compile(output, filename);
};

const {
  decodePaperHoldingQuotes,
  paperHoldingKey,
  paperPortfolioValuation,
  requestPaperHoldingQuotes,
} = require('../lib/paper-trading/valuation.ts');

const holdings = [
  {
    exchange: 'NSE',
    symbolToken: '11536',
    tradingSymbol: 'TCS-EQ',
    quantity: 2,
    costBasisPaise: 500_000,
    averageCostPaise: 250_000,
  },
];

test('trusted holding quotes produce current value and charge-inclusive unrealized pnl', () => {
  const quotes = decodePaperHoldingQuotes(
    JSON.stringify({
      version: 1,
      paper: true,
      quotes: [
        {
          exchange: 'NSE',
          symbol_token: '11536',
          trading_symbol: 'TCS-EQ',
          price_paise: 260_000,
          quote_time: '2026-08-10T05:04:54+00:00',
          provider: 'Angel One SmartAPI',
        },
      ],
    })
  );

  assert.deepEqual(paperPortfolioValuation(holdings, quotes), {
    marketValuePaise: 520_000,
    unrealizedPnlPaise: 20_000,
    quoteCount: 1,
    complete: true,
    latestQuoteTime: '2026-08-10T05:04:54+00:00',
  });
  assert.equal(quotes[paperHoldingKey(holdings[0])].provider, 'Angel One SmartAPI');
});

test('missing quotes never fabricate a complete market value', () => {
  assert.deepEqual(paperPortfolioValuation(holdings, {}), {
    marketValuePaise: 0,
    unrealizedPnlPaise: 0,
    quoteCount: 0,
    complete: false,
    latestQuoteTime: null,
  });
});

test('quote RPC sends only public holding identifiers to the connected agent', async () => {
  const calls = [];
  const participant = {
    async performRpc(options) {
      calls.push(options);
      return '{"version":1,"paper":true,"quotes":[]}';
    },
  };

  const result = await requestPaperHoldingQuotes(participant, 'agent-1', holdings);

  assert.deepEqual(result, {});
  assert.deepEqual(calls, [
    {
      destinationIdentity: 'agent-1',
      method: 'fined.paper.v1.quote_holdings',
      payload: JSON.stringify({
        version: 1,
        paper: true,
        holdings: [
          {
            exchange: 'NSE',
            symbol_token: '11536',
            trading_symbol: 'TCS-EQ',
            quantity: 2,
          },
        ],
      }),
      responseTimeout: 10_000,
    },
  ]);
});

test('quote response rejects extra fields and non-integer paise', () => {
  for (const quote of [
    {
      exchange: 'NSE',
      symbol_token: '11536',
      trading_symbol: 'TCS-EQ',
      price_paise: 260_000.5,
      quote_time: '2026-08-10T05:04:54+00:00',
      provider: 'Angel One SmartAPI',
    },
    {
      exchange: 'NSE',
      symbol_token: '11536',
      trading_symbol: 'TCS-EQ',
      price_paise: 260_000,
      quote_time: '2026-08-10T05:04:54+00:00',
      provider: 'Angel One SmartAPI',
      access_token: 'secret',
    },
  ]) {
    assert.throws(() =>
      decodePaperHoldingQuotes(JSON.stringify({ version: 1, paper: true, quotes: [quote] }))
    );
  }
});
