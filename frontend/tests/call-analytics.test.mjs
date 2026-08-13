import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  module._compile(output, filename);
};

const { decodeCallAnalyticsSummary } = require('../lib/call-analytics.ts');
const frontendRoot = join(import.meta.dirname, '..');

function validSummary(overrides = {}) {
  return {
    version: 1,
    success_definition: 'The learner completed one verified financial learning action.',
    totals: {
      total_calls: 2,
      successful_calls: 1,
      failed_calls: 1,
      success_rate_percent: 50,
    },
    recent_calls: [
      {
        call_id: 'CALL-A1B2-C3D4-E5F6-0123-4567-89AB',
        started_at: '2026-08-13T04:30:00+00:00',
        duration_seconds: 42,
        channel: 'browser',
        outcome: 'successful',
        detail: 'market_quote_delivered',
      },
    ],
    ...overrides,
  };
}

test('decodes real aggregate call data with strict count invariants', () => {
  const summary = decodeCallAnalyticsSummary(validSummary());

  assert.equal(summary.totals.total_calls, 2);
  assert.equal(summary.totals.successful_calls, 1);
  assert.equal(summary.recent_calls[0].channel, 'browser');
  assert.throws(() =>
    decodeCallAnalyticsSummary(
      validSummary({
        totals: {
          total_calls: 9,
          successful_calls: 1,
          failed_calls: 1,
          success_rate_percent: 50,
        },
      })
    )
  );
});

test('rejects caller identifiers, transcripts and arbitrary outcome details', () => {
  for (const unsafe of [
    { ...validSummary(), phone_number: '+919876543210' },
    { ...validSummary(), transcript: 'my OTP is 123456' },
    {
      ...validSummary(),
      recent_calls: [{ ...validSummary().recent_calls[0], caller_id: 'learner-secret' }],
    },
    {
      ...validSummary(),
      recent_calls: [{ ...validSummary().recent_calls[0], detail: 'OTP 123456' }],
    },
    {
      ...validSummary(),
      recent_calls: [
        { ...validSummary().recent_calls[0], outcome: 'failed', detail: 'market_quote_delivered' },
      ],
    },
  ]) {
    assert.throws(() => decodeCallAnalyticsSummary(unsafe));
  }
});

test('analytics route and responsive dashboard expose the Day 8 contract', () => {
  const route = readFileSync(join(frontendRoot, 'app/api/analytics/route.ts'), 'utf8');
  const page = readFileSync(join(frontendRoot, 'app/analytics/page.tsx'), 'utf8');
  const dashboard = readFileSync(
    join(frontendRoot, 'components/analytics/call-analytics-dashboard.tsx'),
    'utf8'
  );
  const nav = readFileSync(join(frontendRoot, 'components/app/site-nav.tsx'), 'utf8');

  assert.match(route, /public-summary\.json/);
  assert.match(route, /no-store/);
  for (const label of ['Total calls', 'Successful calls', 'Failed calls', 'Success rate']) {
    assert.ok(dashboard.includes(label), `missing metric: ${label}`);
  }
  assert.match(dashboard, /setInterval/);
  assert.match(dashboard, /Recent calls/);
  assert.match(dashboard, /No phone numbers, participant identities or transcripts/);
  assert.match(page, /CallAnalyticsDashboard/);
  assert.match(nav, /href:\s*['"]\/analytics['"]/);
});
