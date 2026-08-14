import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8');
  module._compile(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      fileName: filename,
    }).outputText,
    filename
  );
};

const { formatOfficialSourceLinks } = require('../lib/official-source-links.ts');

const incomeTaxActUrl =
  'https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf';
const incomeTaxActTitle = 'Income-tax Act, 2025 as amended by Finance Act, 2026';

test('relabels a known official raw Markdown link without nested parentheses', () => {
  assert.equal(
    formatOfficialSourceLinks(
      `Under the ([${incomeTaxActUrl}](${incomeTaxActUrl})), effective 1 April 2026.`
    ),
    `Under the [${incomeTaxActTitle}](${incomeTaxActUrl}), effective 1 April 2026.`
  );
});

test('relabels a known bare official URL and preserves unknown links', () => {
  assert.equal(
    formatOfficialSourceLinks(`Source: ${incomeTaxActUrl}`),
    `Source: [${incomeTaxActTitle}](${incomeTaxActUrl})`
  );
  assert.equal(
    formatOfficialSourceLinks('See [broker guide](https://example.com/guide).'),
    'See [broker guide](https://example.com/guide).'
  );
});

test('keeps an already titled official link stable', () => {
  const titled = `[${incomeTaxActTitle}](${incomeTaxActUrl})`;
  assert.equal(formatOfficialSourceLinks(titled), titled);
  assert.equal(formatOfficialSourceLinks(formatOfficialSourceLinks(titled)), titled);
});
