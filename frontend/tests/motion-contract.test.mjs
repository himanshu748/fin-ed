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

function loadHook(relativePath, dependencies) {
  const output = ts.transpileModule(read(relativePath), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const compiledModule = { exports: {} };

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected hook dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );

  return compiledModule.exports;
}

function createEffectHarness() {
  const effects = [];
  return {
    react: {
      useEffect(effect) {
        effects.push(effect);
      },
    },
    effect(index = 0) {
      return effects[index];
    },
  };
}

function createGsapHarness({ reduceMotion = false } = {}) {
  const state = {
    contextReverts: 0,
    mediaReverts: 0,
    sets: [],
    timelines: [],
  };
  const gsap = {
    context(setup) {
      setup();
      return {
        revert() {
          state.contextReverts += 1;
        },
      };
    },
    matchMedia() {
      let cleanup;
      return {
        add(_conditions, setup) {
          cleanup = setup({
            conditions: { allowMotion: !reduceMotion, reduceMotion },
          });
        },
        revert() {
          state.mediaReverts += 1;
          cleanup?.();
        },
      };
    },
    set(targets, vars) {
      state.sets.push({ targets, vars });
    },
    timeline(options) {
      const timeline = {
        fromToCalls: [],
        killCalls: 0,
        options,
        playCalls: 0,
        reverseCalls: 0,
        fromTo(targets, from, to) {
          this.fromToCalls.push({ targets, from, to });
          return this;
        },
        kill() {
          this.killCalls += 1;
          return this;
        },
        play() {
          this.playCalls += 1;
          return this;
        },
        reverse() {
          this.reverseCalls += 1;
          return this;
        },
      };
      state.timelines.push(timeline);
      return timeline;
    },
    utils: {
      toArray(_selector, scope) {
        return [scope];
      },
    },
  };

  return { gsap, state };
}

function installBrowserHarness() {
  const previousObserver = globalThis.IntersectionObserver;
  const previousWindow = globalThis.window;
  const observers = [];

  globalThis.window = { innerHeight: 800 };
  globalThis.IntersectionObserver = class MockIntersectionObserver {
    constructor(callback, options) {
      this.callback = callback;
      this.disconnectCalls = 0;
      this.observed = [];
      this.options = options;
      observers.push(this);
    }

    disconnect() {
      this.disconnectCalls += 1;
    }

    observe(target) {
      this.observed.push(target);
    }

    intersect(isIntersecting = true) {
      this.callback([{ isIntersecting }]);
    }
  };

  return {
    observers,
    restore() {
      if (previousObserver === undefined) delete globalThis.IntersectionObserver;
      else globalThis.IntersectionObserver = previousObserver;
      if (previousWindow === undefined) delete globalThis.window;
      else globalThis.window = previousWindow;
    },
  };
}

function renderGsapHook({ rect, reduceMotion = false, start = 'top 86%', once = true }) {
  const effects = createEffectHarness();
  const gsapHarness = createGsapHarness({ reduceMotion });
  const { useGsapReveal } = loadHook(
    'hooks/use-gsap-reveal.ts',
    new Map([
      ['react', effects.react],
      ['gsap', { gsap: gsapHarness.gsap }],
    ])
  );
  const scope = {
    getBoundingClientRect() {
      return rect;
    },
  };

  useGsapReveal({ current: scope }, { once, start });
  return { ...gsapHarness, effect: effects.effect(), scope };
}

function createStatefulReactHarness() {
  const effectSlots = [];
  const refs = [];
  const states = [];
  let cursor = 0;
  let pendingEffects = [];

  return {
    react: {
      useEffect(effect, dependencies) {
        const index = cursor++;
        const previous = effectSlots[index];
        const changed =
          !previous ||
          dependencies.length !== previous.dependencies.length ||
          dependencies.some(
            (dependency, dependencyIndex) =>
              !Object.is(dependency, previous.dependencies[dependencyIndex])
          );
        if (changed) pendingEffects.push({ dependencies, effect, index });
      },
      useRef(initialValue) {
        const index = cursor++;
        refs[index] ??= { current: initialValue };
        return refs[index];
      },
      useState(initialValue) {
        const index = cursor++;
        if (!(index in states)) {
          states[index] = typeof initialValue === 'function' ? initialValue() : initialValue;
        }
        return [
          states[index],
          (nextValue) => {
            states[index] = typeof nextValue === 'function' ? nextValue(states[index]) : nextValue;
          },
        ];
      },
    },
    beginRender() {
      cursor = 0;
      pendingEffects = [];
    },
    flushEffects() {
      for (const pending of pendingEffects) {
        effectSlots[pending.index]?.cleanup?.();
        effectSlots[pending.index] = {
          cleanup: pending.effect(),
          dependencies: pending.dependencies,
        };
      }
      pendingEffects = [];
    },
    unmount() {
      for (const slot of effectSlots) slot?.cleanup?.();
    },
  };
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

test('an initially visible reveal stays in its final state without a hidden timeline', () => {
  const browser = installBrowserHarness();
  try {
    const { effect, state, scope } = renderGsapHook({
      rect: { bottom: 260, top: 40 },
    });
    const cleanup = effect();

    assert.equal(state.timelines.length, 0);
    assert.equal(browser.observers.length, 0);
    assert.deepEqual(state.sets, [{ targets: [scope], vars: { autoAlpha: 1, y: 0 } }]);

    cleanup();
    assert.equal(state.mediaReverts, 1);
    assert.equal(state.contextReverts, 1);
  } finally {
    browser.restore();
  }
});

test('a below-fold reveal normalizes invalid starts and uses the Ledger duration', () => {
  const browser = installBrowserHarness();
  try {
    const { effect, state } = renderGsapHook({
      rect: { bottom: 1100, top: 900 },
      start: 'somewhere around the fold',
    });
    const cleanup = effect();

    assert.equal(state.timelines.length, 1);
    assert.equal(state.timelines[0].fromToCalls[0].to.duration, 0.22);
    assert.equal(browser.observers.length, 1);
    assert.equal(browser.observers[0].options.rootMargin, '0px 0px -14% 0px');
    assert.deepEqual(browser.observers[0].observed.length, 1);

    cleanup();
  } finally {
    browser.restore();
  }
});

test('once reveal and Strict Mode-style remount clean every lifecycle resource', () => {
  const browser = installBrowserHarness();
  try {
    const { effect, state } = renderGsapHook({
      rect: { bottom: 1100, top: 900 },
    });

    const firstCleanup = effect();
    browser.observers[0].intersect();
    assert.equal(state.timelines[0].playCalls, 1);
    assert.equal(browser.observers[0].disconnectCalls, 1);
    firstCleanup();

    const secondCleanup = effect();
    browser.observers[1].intersect();
    secondCleanup();

    assert.equal(state.timelines.length, 2);
    assert.ok(state.timelines.every((timeline) => timeline.killCalls >= 1));
    assert.ok(browser.observers.every((observer) => observer.disconnectCalls >= 2));
    assert.equal(state.mediaReverts, 2);
    assert.equal(state.contextReverts, 2);
  } finally {
    browser.restore();
  }
});

test('reduced motion keeps the final reveal state and skips observer setup', () => {
  const browser = installBrowserHarness();
  try {
    const { effect, state, scope } = renderGsapHook({
      rect: { bottom: 1100, top: 900 },
      reduceMotion: true,
    });
    const cleanup = effect();

    assert.equal(state.timelines.length, 0);
    assert.equal(browser.observers.length, 0);
    assert.deepEqual(state.sets, [{ targets: [scope], vars: { autoAlpha: 1, y: 0 } }]);

    cleanup();
    assert.equal(state.mediaReverts, 1);
    assert.equal(state.contextReverts, 1);
  } finally {
    browser.restore();
  }
});

test('animated numbers cancel the prior tween and return reduced-motion values directly', () => {
  const reactHarness = createStatefulReactHarness();
  const animations = [];
  let reduceMotion = false;
  const { useAnimatedNumber } = loadHook(
    'hooks/use-animated-number.ts',
    new Map([
      ['react', reactHarness.react],
      [
        'animejs',
        {
          animate(target, options) {
            const animation = {
              cancelCalls: 0,
              cancel() {
                this.cancelCalls += 1;
              },
              options,
              target,
            };
            animations.push(animation);
            return animation;
          },
        },
      ],
      ['motion/react', { useReducedMotion: () => reduceMotion }],
    ])
  );

  reactHarness.beginRender();
  assert.equal(useAnimatedNumber(10, { from: 0 }), 0);
  reactHarness.flushEffects();
  assert.equal(animations.length, 1);

  reactHarness.beginRender();
  useAnimatedNumber(20, { from: 0 });
  reactHarness.flushEffects();
  assert.equal(animations[0].cancelCalls, 1);
  assert.equal(animations.length, 2);

  reduceMotion = true;
  reactHarness.beginRender();
  assert.equal(useAnimatedNumber(30, { from: 0 }), 30);
  reactHarness.flushEffects();
  assert.equal(animations[1].cancelCalls, 1);
  assert.equal(animations.length, 2);

  reactHarness.unmount();
});

test('animated numbers hydrate at the final value without an initial count-up', () => {
  const reactHarness = createStatefulReactHarness();
  const animations = [];
  const { useAnimatedNumber } = loadHook(
    'hooks/use-animated-number.ts',
    new Map([
      ['react', reactHarness.react],
      [
        'animejs',
        {
          animate(target, options) {
            animations.push({ options, target });
            return { cancel() {} };
          },
        },
      ],
      ['motion/react', { useReducedMotion: () => false }],
    ])
  );

  reactHarness.beginRender();
  assert.equal(useAnimatedNumber(7_049_300), 7_049_300);
  reactHarness.flushEffects();
  assert.equal(animations.length, 1);
  assert.equal(animations[0].target.value, 7_049_300);

  reactHarness.unmount();
});
