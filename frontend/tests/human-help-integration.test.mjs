import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

const frontendRoot = join(import.meta.dirname, '..');

function read(relativePath) {
  return readFileSync(join(frontendRoot, relativePath), 'utf8');
}

test('app mounts the participant-scoped human-help provider', () => {
  const app = read('components/app/app.tsx');

  assert.match(app, /HumanHelpProvider/);
  assert.match(app, /<HumanHelpProvider>/);
  assert.match(app, /<PaperTradingProvider>/);
});

test('connected voice workspace exposes and automatically opens human help', () => {
  const session = read('components/app/fin-ed-session-view.tsx');

  for (const contract of [
    'useHumanHelp',
    'HumanHelpDashboard',
    'Human help',
    'humanHelp.isOpen',
    'humanHelp.open',
    'humanHelp.close',
  ]) {
    assert.ok(session.includes(contract), `missing human-help workspace contract: ${contract}`);
  }
  assert.match(session, /<AgentControlBar/);
});

test('human-help copy never claims confirmed fraud or a guaranteed response time', () => {
  const dashboard = read('components/human-help/escalation-dashboard.tsx').toLowerCase();

  assert.match(dashboard, /suspected fraud/);
  assert.match(dashboard, /response\s+time is not guaranteed/);
  assert.doesNotMatch(dashboard, /confirmed fraud/);
  assert.doesNotMatch(dashboard, /will reply/);
  assert.doesNotMatch(dashboard, /[\u2013\u2014]/);
});
