import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

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

const gsapHook = read('hooks/use-gsap-reveal.ts');
const numberHook = read('hooks/use-animated-number.ts');
const packageManifest = read('package.json');
const reveal = read('components/app/reveal.tsx');

test('installs isolated GSAP and anime.js motion engines', () => {
  includesAll(packageManifest, ['"gsap"', '"animejs"'], 'missing motion dependency');
});

test('GSAP hook uses matchMedia, context, and cleanup', () => {
  includesAll(
    gsapHook,
    ['gsap.matchMedia()', 'gsap.context(', 'IntersectionObserver', '.revert()', '.kill()'],
    'missing scoped GSAP lifecycle'
  );
  assert.ok(!gsapHook.includes('ScrollTrigger'), 'reveal must use the native observer');
});

test('anime number hook bypasses animation for reduced motion', () => {
  includesAll(
    numberHook,
    ['useReducedMotion', 'animate(', 'cancel()'],
    'missing accessible number animation lifecycle'
  );
});

test('the two engines have separate target ownership', () => {
  assert.ok(!numberHook.includes('autoAlpha'));
  assert.ok(!gsapHook.includes('innerHTML'));
});

test('Reveal delegates to the GSAP hook without pre-hydration hiding', () => {
  includesAll(reveal, ['useGsapReveal(', 'ref={nodeRef}'], 'missing Reveal hook delegation');
  assert.ok(!reveal.includes('.animate('), 'Reveal must not retain Web Animations');
  assert.ok(!reveal.includes('opacity-0'), 'Reveal must server-render visibly');
  assert.ok(!reveal.includes('style={{'), 'Reveal must not inline a hidden server state');
});
