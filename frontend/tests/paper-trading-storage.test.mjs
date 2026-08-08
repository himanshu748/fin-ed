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

test('reports a missing browser portfolio without creating one', () => {
  const storage = memoryStorage();

  assert.deepEqual(loadPaperPortfolio(storage), { status: 'missing' });
});

test('persists and strictly reloads a valid version-one portfolio', () => {
  const storage = memoryStorage();
  const portfolio = createPaperPortfolio(NOW, 'portfolio-1');

  assert.deepEqual(savePaperPortfolio(storage, portfolio), { status: 'saved', portfolio });
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

test('reports unavailable storage when browser access throws', () => {
  const unavailable = {
    getItem() {
      throw new Error('blocked');
    },
    setItem() {
      throw new Error('blocked');
    },
  };

  assert.deepEqual(loadPaperPortfolio(unavailable), { status: 'unavailable' });
  assert.deepEqual(savePaperPortfolio(unavailable, createPaperPortfolio(NOW, 'portfolio-1')), {
    status: 'unavailable',
  });
});

test('keeps the newer revision already written by another tab', () => {
  const storage = memoryStorage();
  const older = createPaperPortfolio(NOW, 'portfolio-1');
  const newer = reducePaperPortfolio(older, { type: 'reset', now: '2026-08-08T00:01:00.000Z' });

  assert.equal(savePaperPortfolio(storage, newer).status, 'saved');
  assert.deepEqual(savePaperPortfolio(storage, older), { status: 'stale', portfolio: newer });
  assert.deepEqual(loadPaperPortfolio(storage), { status: 'ready', portfolio: newer });
});
