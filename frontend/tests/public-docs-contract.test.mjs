import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

const repoRoot = join(import.meta.dirname, '..', '..');
const readRepo = (path) => readFileSync(join(repoRoot, path), 'utf8');

test('keeps one canonical setup guide with truthful Day 10 claims', () => {
  const readme = readRepo('README.md');
  for (const required of [
    'Murf Falcon is the fastest TTS API',
    'frontend/public/images/day-10/fined-architecture.svg',
    'frontend/public/images/day-10/landing-proof.png',
    'LIVEKIT_URL',
    'MURF_API_KEY',
    'DEEPGRAM_API_KEY',
    'GOOGLE_API_KEY',
    'AGENT_NAME=my-agent',
    'uv run dotenv -f .env.local run -- python src/agent.py start',
    'pnpm dev --port 3001',
    'uv run pytest -q --ignore=tests/test_agent.py',
    'node --test tests/*.test.mjs',
    'No real broker order API is called',
    'TaxEd',
    'Anusha',
    'hi-LATN',
  ]) {
    assert.ok(readme.includes(required), `README missing: ${required}`);
  }
  assert.ok(!readme.includes('backend/README.md'));
  assert.ok(!readme.includes('frontend/README.md'));
  assert.ok(!readme.includes('docs/DESIGN.md'));
  assert.ok(!/[—–]/u.test(readme), 'README contains a Unicode dash');
});

test('keeps a current evidence-backed red-team record', () => {
  const record = readRepo('RED_TEAM.md');
  assert.ok(record.includes('Verified on 15 August 2026'));
  assert.ok(record.includes('tests/test_guardrails.py'));
  assert.ok(record.includes('tests/test_handoff.py'));
  assert.ok(record.includes('tests/test_tax_rules.py'));
  assert.ok(record.includes('tests/test_outbound.py'));
  assert.ok(record.includes('Real broker order'));
  assert.ok(record.includes('Broker identifier handoff'));
  assert.ok(record.includes('Unverified tax rule'));
  assert.ok(!/[—–]/u.test(record), 'red-team record contains a Unicode dash');
});

test('publishes only the approved Markdown files', () => {
  const tracked = execFileSync('git', ['ls-files', '*.md'], {
    cwd: repoRoot,
    encoding: 'utf8',
  })
    .trim()
    .split('\n')
    .filter(Boolean)
    .sort();
  assert.deepEqual(tracked, ['README.md', 'RED_TEAM.md']);
});
