import * as jsxRuntime from 'react/jsx-runtime';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const frontendRoot = join(import.meta.dirname, '..');

function compile(relativePath, dependencies) {
  const output = ts.transpileModule(readFileSync(join(frontendRoot, relativePath), 'utf8'), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const compiledModule = { exports: {} };

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected ${relativePath} dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );

  return compiledModule.exports;
}

function textContent(node) {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textContent).join('');
  return textContent(node.props?.children);
}

function findElement(node, predicate) {
  if (node === null || node === undefined || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findElement(child, predicate);
      if (found) return found;
    }
    return null;
  }
  if (predicate(node)) return node;
  return findElement(node.props?.children, predicate);
}

function dependenciesChanged(previous, next) {
  if (previous === undefined || next === undefined || previous.length !== next.length) return true;
  return previous.some((value, index) => !Object.is(value, next[index]));
}

function createSessionHarness({
  initialView = 'session',
  reduceMotion = false,
  previousSessions = [],
} = {}) {
  const states = [];
  const refs = [];
  const layoutEffects = [];
  const passiveEffects = [];
  const timelines = [];
  let stateCursor = 0;
  let refCursor = 0;
  let layoutCursor = 0;
  let passiveCursor = 0;
  let pendingLayoutEffects = [];
  let pendingPassiveEffects = [];
  let triggerFocusCalls = 0;
  let dashboardFocusCalls = 0;
  let sessionHeadingFocusCalls = 0;
  let contextReverts = 0;
  let timelineKills = 0;
  let newSessionCalls = 0;

  const trigger = { focus: () => (triggerFocusCalls += 1) };
  const dashboardHeading = { focus: () => (dashboardFocusCalls += 1) };
  const workspace = {
    querySelector(selector) {
      return selector === 'h1' ? dashboardHeading : null;
    },
  };
  const sessionHeading = { focus: () => (sessionHeadingFocusCalls += 1) };
  const paperTrading = {
    view: initialView,
    openDashboard() {},
  };

  function scheduleEffect(records, pending, index, effect, dependencies) {
    if (dependenciesChanged(records[index]?.dependencies, dependencies)) {
      pending.push({ index, effect, dependencies });
    }
  }

  function flushEffects(records, pending) {
    for (const item of pending) {
      records[item.index]?.cleanup?.();
      const cleanup = item.effect();
      records[item.index] = {
        cleanup: typeof cleanup === 'function' ? cleanup : null,
        dependencies: item.dependencies,
        effect: item.effect,
      };
    }
    pending.length = 0;
  }

  const react = {
    useEffect(effect, dependencies) {
      const index = passiveCursor;
      passiveCursor += 1;
      scheduleEffect(passiveEffects, pendingPassiveEffects, index, effect, dependencies);
    },
    useLayoutEffect(effect, dependencies) {
      const index = layoutCursor;
      layoutCursor += 1;
      scheduleEffect(layoutEffects, pendingLayoutEffects, index, effect, dependencies);
    },
    useRef(initialValue) {
      const index = refCursor;
      refCursor += 1;
      if (!(index in refs)) {
        const current =
          index === 0
            ? trigger
            : index === 2
              ? workspace
              : index === 3
                ? sessionHeading
                : initialValue;
        refs[index] = { current };
      }
      return refs[index];
    },
    useState(initialValue) {
      const index = stateCursor;
      stateCursor += 1;
      if (!(index in states)) states[index] = initialValue;
      return [
        states[index],
        (value) => {
          states[index] = typeof value === 'function' ? value(states[index]) : value;
        },
      ];
    },
  };

  const gsap = {
    context(callback, scope) {
      assert.equal(scope, workspace);
      callback();
      return { revert: () => (contextReverts += 1) };
    },
    timeline(options) {
      const timeline = {
        options,
        from: null,
        to: null,
        target: null,
        killed: false,
        fromTo(target, from, to) {
          timeline.target = target;
          timeline.from = from;
          timeline.to = to;
          return timeline;
        },
        kill() {
          timeline.killed = true;
          timelineKills += 1;
        },
      };
      timelines.push(timeline);
      return timeline;
    },
  };

  const AgentChatTranscript = () => null;
  const AgentControlBar = () => null;
  const PaperTradingDashboard = () => null;
  const icon = () => null;
  const iconModule = new Proxy({}, { get: () => icon });
  const connectionState = {
    Connected: 'connected',
    Disconnected: 'disconnected',
    Reconnecting: 'reconnecting',
    SignalReconnecting: 'signal-reconnecting',
  };
  const FinEdSessionView = compile(
    'components/app/fin-ed-session-view.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', jsxRuntime],
      ['gsap', { gsap }],
      ['livekit-client', { ConnectionState: connectionState }],
      ['lucide-react', iconModule],
      ['motion/react', { useReducedMotion: () => reduceMotion }],
      [
        '@livekit/components-react',
        {
          useAgent: () => ({ state: 'idle' }),
          useSessionContext: () => ({
            connectionState: connectionState.Connected,
            isConnected: true,
            room: {
              name: 'voice_assistant_room_550e8400-e29b-41d4-a716-446655440000',
            },
          }),
          useSessionMessages: () => ({ messages: [] }),
          useVoiceAssistant: () => ({ audioTrack: undefined }),
        },
      ],
      [
        '@/components/agents-ui/agent-audio-visualizer-bar',
        { AgentAudioVisualizerBar: () => null },
      ],
      ['@/components/agents-ui/agent-chat-transcript', { AgentChatTranscript }],
      ['@/components/agents-ui/agent-control-bar', { AgentControlBar }],
      ['@/components/paper-trading/paper-trading-dashboard', { PaperTradingDashboard }],
      [
        '@/components/paper-trading/paper-trading-provider',
        { usePaperTrading: () => paperTrading },
      ],
      ['@/lib/learning-modes', { LEARNING_MODES: [{ value: 'general', label: 'Ask Anything' }] }],
      [
        '@/lib/voice-session-history',
        {
          archiveVoiceSession: () => ({ status: 'saved', sessions: previousSessions }),
          browserVoiceSessionStorage: () => ({}),
          loadVoiceSessions: () => ({ status: 'ready', sessions: previousSessions }),
          toArchivedVoiceMessages: () => [],
        },
      ],
    ])
  ).FinEdSessionView;

  return {
    AgentChatTranscript,
    AgentControlBar,
    PaperTradingDashboard,
    paperTrading,
    timelines,
    render() {
      stateCursor = 0;
      refCursor = 0;
      layoutCursor = 0;
      passiveCursor = 0;
      pendingLayoutEffects = [];
      pendingPassiveEffects = [];
      const tree = FinEdSessionView({
        appConfig: {},
        learningMode: 'general',
        onNewSession: async () => {
          newSessionCalls += 1;
        },
      });
      flushEffects(layoutEffects, pendingLayoutEffects);
      return tree;
    },
    flushPassiveEffects() {
      flushEffects(passiveEffects, pendingPassiveEffects);
    },
    unmount() {
      for (const record of [...layoutEffects, ...passiveEffects]) record?.cleanup?.();
    },
    strictModeReplayLayoutEffects() {
      for (const record of layoutEffects) record?.cleanup?.();
      for (let index = 0; index < layoutEffects.length; index += 1) {
        const record = layoutEffects[index];
        if (!record) continue;
        const cleanup = record.effect();
        layoutEffects[index] = {
          ...record,
          cleanup: typeof cleanup === 'function' ? cleanup : null,
        };
      }
    },
    focusCalls() {
      return { triggerFocusCalls, dashboardFocusCalls, sessionHeadingFocusCalls };
    },
    cleanupCalls() {
      return { contextReverts, timelineKills };
    },
    newSessionCalls() {
      return newSessionCalls;
    },
  };
}

function loadViewController({ agentState, isConnected, startError, startPromise }) {
  const stateWrites = [];
  let stateIndex = 0;
  let endCalls = 0;
  let startCalls = 0;
  const session = {
    isConnected,
    start: async () => {
      startCalls += 1;
      if (startError) throw startError;
      if (startPromise) return startPromise;
    },
    end: async () => {
      endCalls += 1;
    },
  };
  const react = {
    useEffect(effect) {
      effect();
    },
    useLayoutEffect(effect) {
      effect();
    },
    useRef(value) {
      return { current: value };
    },
    useState(initialValue) {
      const index = stateIndex;
      stateIndex += 1;
      return [initialValue, (value) => stateWrites.push({ index, value })];
    },
  };
  const output = ts.transpileModule(
    readFileSync(join(frontendRoot, 'components/app/view-controller.tsx'), 'utf8'),
    {
      compilerOptions: {
        jsx: ts.JsxEmit.ReactJSX,
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }
  ).outputText;
  const compiledModule = { exports: {} };
  const dependencies = new Map([
    ['react', react],
    ['react/jsx-runtime', jsxRuntime],
    [
      'motion/react',
      { AnimatePresence: 'div', motion: { div: 'div' }, useReducedMotion: () => true },
    ],
    [
      '@livekit/components-react',
      { useAgent: () => ({ state: agentState }), useSessionContext: () => session },
    ],
    [
      '@/components/app/fin-ed-session-view',
      { FinEdSessionView: (props) => jsxRuntime.jsx('session-view', props) },
    ],
    ['@/components/app/welcome-view', { WelcomeView: () => null }],
  ]);

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      const dependency = dependencies.get(specifier);
      if (!dependency) throw new Error(`Unexpected ViewController dependency: ${specifier}`);
      return dependency;
    },
    compiledModule,
    compiledModule.exports
  );

  const view = compiledModule.exports.ViewController({
    appConfig: {},
    learningMode: 'general',
    onLearningModeChange: () => undefined,
  });

  return {
    get endCalls() {
      return endCalls;
    },
    get startCalls() {
      return startCalls;
    },
    stateWrites,
    view,
    exports: compiledModule.exports,
  };
}

test('a failed agent state after the room disconnected is not reported as a connection failure', () => {
  const result = loadViewController({ agentState: 'failed', isConnected: false });

  assert.equal(result.endCalls, 0);
  assert.deepEqual(result.stateWrites, []);
});

test('microphone permission failures explain how to retry without making account-access claims', async () => {
  const result = loadViewController({
    agentState: 'idle',
    isConnected: false,
    startError: Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' }),
  });

  const message = result.exports.connectionErrorMessageFor(
    Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' })
  );
  assert.equal(
    message,
    'Microphone access is required for a voice call. Allow microphone access in your browser settings, then try connecting again.'
  );
  assert.doesNotMatch(message, /broker|credential|account access/i);

  const welcome = findElement(
    result.view,
    (element) => typeof element.props?.onStartCall === 'function'
  );
  assert.ok(welcome, 'welcome view must expose the start action');
  await welcome.props.onStartCall();
  assert.ok(
    result.stateWrites.some((write) => write.index === 1 && write.value === message),
    'the actionable microphone message must be stored for the welcome screen'
  );
});

test('generic startup failures report a voice connection failure', () => {
  const result = loadViewController({ agentState: 'idle', isConnected: false });

  assert.equal(
    result.exports.connectionErrorMessageFor(new Error('signalling timed out')),
    'Voice connection failed. Check your network and try again.'
  );
});

test('starting a new session ends the current room and connects a fresh room', async () => {
  const result = loadViewController({ agentState: 'idle', isConnected: true });
  const sessionView = findElement(
    result.view,
    (element) => typeof element.props?.onNewSession === 'function'
  );
  assert.ok(sessionView, 'connected view must receive the new session action');

  await sessionView.props.onNewSession();

  assert.equal(result.endCalls, 1);
  assert.equal(result.startCalls, 1);
});

test('a stalled LiveKit start times out, ends the room, and unlocks retry', async () => {
  const neverSettles = new Promise(() => undefined);
  const result = loadViewController({
    agentState: 'idle',
    isConnected: false,
    startPromise: neverSettles,
  });
  const welcome = findElement(
    result.view,
    (element) => typeof element.props?.onStartCall === 'function'
  );
  assert.ok(welcome, 'welcome view must expose the start action');

  const nativeSetTimeout = globalThis.setTimeout;
  const nativeClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = (callback) => {
    queueMicrotask(callback);
    return 1;
  };
  globalThis.clearTimeout = () => undefined;

  try {
    const outcome = await Promise.race([
      welcome.props.onStartCall().then(() => 'settled'),
      new Promise((resolve) => nativeSetTimeout(() => resolve('hung'), 20)),
    ]);
    assert.equal(outcome, 'settled', 'the start action must not stay pending forever');
  } finally {
    globalThis.setTimeout = nativeSetTimeout;
    globalThis.clearTimeout = nativeClearTimeout;
  }

  assert.equal(result.endCalls, 1);
  assert.ok(
    result.stateWrites.some(
      (write) =>
        write.index === 1 &&
        write.value === 'Voice connection failed. Check your network and try again.'
    )
  );
  assert.ok(
    result.stateWrites.some((write) => write.index === 0 && write.value === false),
    'the connecting state must be cleared so retry is enabled'
  );
});

test('opening the paper workspace does not end the live voice session', () => {
  let endCalls = 0;
  let openDashboardCalls = 0;
  const connectionState = {
    Connected: 'connected',
    Disconnected: 'disconnected',
    Reconnecting: 'reconnecting',
    SignalReconnecting: 'signal-reconnecting',
  };
  const paperTrading = {
    view: 'session',
    openDashboard() {
      openDashboardCalls += 1;
    },
  };
  const icon = () => null;
  const iconModule = new Proxy({}, { get: () => icon });
  const react = {
    useEffect(effect) {
      effect();
    },
    useLayoutEffect(effect) {
      effect();
    },
    useRef(value) {
      return { current: value };
    },
    useState(value) {
      return [value, () => undefined];
    },
  };
  const FinEdSessionView = compile(
    'components/app/fin-ed-session-view.tsx',
    new Map([
      ['react', react],
      ['react/jsx-runtime', jsxRuntime],
      ['gsap', { gsap: {} }],
      ['livekit-client', { ConnectionState: connectionState }],
      ['lucide-react', iconModule],
      ['motion/react', { useReducedMotion: () => true }],
      [
        '@livekit/components-react',
        {
          useAgent: () => ({ state: 'idle' }),
          useSessionContext: () => ({
            connectionState: connectionState.Connected,
            isConnected: true,
            room: {
              name: 'voice_assistant_room_550e8400-e29b-41d4-a716-446655440000',
            },
            end() {
              endCalls += 1;
            },
          }),
          useSessionMessages: () => ({ messages: [] }),
          useVoiceAssistant: () => ({ audioTrack: undefined }),
        },
      ],
      [
        '@/components/agents-ui/agent-audio-visualizer-bar',
        { AgentAudioVisualizerBar: () => null },
      ],
      ['@/components/agents-ui/agent-chat-transcript', { AgentChatTranscript: () => null }],
      ['@/components/agents-ui/agent-control-bar', { AgentControlBar: () => null }],
      ['@/components/paper-trading/paper-trading-dashboard', { PaperTradingDashboard: () => null }],
      [
        '@/components/paper-trading/paper-trading-provider',
        { usePaperTrading: () => paperTrading },
      ],
      ['@/lib/learning-modes', { LEARNING_MODES: [{ value: 'general', label: 'Ask Anything' }] }],
      [
        '@/lib/voice-session-history',
        {
          archiveVoiceSession: () => ({ status: 'unavailable' }),
          browserVoiceSessionStorage: () => null,
          loadVoiceSessions: () => ({ status: 'unavailable' }),
          toArchivedVoiceMessages: () => [],
        },
      ],
    ])
  ).FinEdSessionView;

  const view = FinEdSessionView({ appConfig: {}, learningMode: 'general' });
  const paperTrigger = findElement(
    view,
    (element) => element.type === 'button' && textContent(element).includes('Paper trading')
  );
  assert.ok(paperTrigger, 'Paper trading trigger must render');
  paperTrigger.props.onClick();

  assert.equal(openDashboardCalls, 1);
  assert.equal(endCalls, 0);
});

test('the connected workspace shows and copies a safe ChatGPT-style session ID', async () => {
  // Catches hidden session identity or accidental exposure of the persistent learner ID.
  const harness = createSessionHarness({ reduceMotion: true });
  let view = harness.render();
  const sessionCode = findElement(view, (element) => element.props?.['data-session-id']);
  const copyButton = findElement(
    view,
    (element) => element.type === 'button' && element.props?.['aria-label'] === 'Copy session ID'
  );

  assert.ok(sessionCode, 'connected workspace must expose its support-safe session ID');
  assert.equal(textContent(sessionCode), '550e8400-e29b-41d4-a716-446655440000');
  assert.ok(copyButton, 'session ID must have a keyboard-accessible copy action');
  assert.doesNotMatch(textContent(view), /voice_assistant_user_/);

  const writes = [];
  const nativeClipboard = globalThis.navigator.clipboard;
  Object.defineProperty(globalThis.navigator, 'clipboard', {
    configurable: true,
    value: { writeText: async (value) => writes.push(value) },
  });
  try {
    await copyButton.props.onClick();
    view = harness.render();
  } finally {
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: nativeClipboard,
    });
  }

  assert.deepEqual(writes, ['550e8400-e29b-41d4-a716-446655440000']);
  const copiedButton = findElement(
    view,
    (element) => element.type === 'button' && element.props?.['aria-label'] === 'Copy session ID'
  );
  assert.match(textContent(copiedButton), /Copied/);
});

test('the connected workspace switches between live and saved browser sessions', async () => {
  const previousSession = {
    sessionId: '67e55044-10b1-426f-9247-bb680e5fe0c8',
    learningMode: 'stocks',
    startedAt: 1_754_638_000_000,
    updatedAt: 1_754_638_001_000,
    messages: [
      {
        id: 'saved-1',
        role: 'user',
        text: 'Explain delivery trading charges',
        timestamp: 1_754_638_000_000,
      },
      {
        id: 'saved-2',
        role: 'assistant',
        text: 'Delivery brokerage and statutory charges are separate.',
        timestamp: 1_754_638_001_000,
      },
    ],
  };
  const harness = createSessionHarness({ reduceMotion: true, previousSessions: [previousSession] });
  let view = harness.render();
  harness.flushPassiveEffects();
  view = harness.render();

  const sessionsButton = findElement(
    view,
    (element) => element.type === 'button' && element.props?.['aria-label'] === 'Open sessions'
  );
  assert.ok(sessionsButton, 'the live workspace must expose the session switcher');
  sessionsButton.props.onClick();
  view = harness.render();

  const savedSessionButton = findElement(
    view,
    (element) => element.type === 'button' && textContent(element).includes('67e55044')
  );
  assert.ok(savedSessionButton, 'saved session must be selectable by its safe session ID');
  savedSessionButton.props.onClick();
  view = harness.render();
  assert.match(textContent(view), /Read-only browser history/);
  assert.match(textContent(view), /Explain delivery trading charges/);
  assert.match(textContent(view), /Delivery brokerage and statutory charges are separate/);

  const liveButton = findElement(
    view,
    (element) => element.type === 'button' && textContent(element).includes('Back to live')
  );
  assert.ok(liveButton, 'archived transcript must provide a way back to the live call');
  liveButton.props.onClick();
  view = harness.render();
  assert.doesNotMatch(textContent(view), /Read-only browser history/);

  sessionsButton.props.onClick();
  view = harness.render();
  const newSessionButton = findElement(
    view,
    (element) => element.type === 'button' && textContent(element).includes('New session')
  );
  assert.ok(newSessionButton, 'session switcher must expose a new session action');
  await newSessionButton.props.onClick();
  assert.equal(harness.newSessionCalls(), 1);
});

test('a collapsed transcript uses native hidden semantics instead of leaving links tabbable', () => {
  const harness = createSessionHarness({ reduceMotion: true });
  let view = harness.render();
  const controls = findElement(view, (element) => element.type === harness.AgentControlBar);
  assert.ok(controls, 'voice controls must render');

  controls.props.onIsChatOpenChange(false);
  view = harness.render();
  const transcriptWrapper = findElement(view, (element) => {
    const children = Array.isArray(element.props?.children)
      ? element.props.children
      : [element.props?.children];
    return children.some((child) => child?.type === harness.AgentChatTranscript);
  });

  assert.ok(transcriptWrapper, 'transcript wrapper must stay mounted');
  assert.equal(transcriptWrapper.props.hidden, true);
  assert.equal(transcriptWrapper.props.inert, true);
  assert.doesNotMatch(transcriptWrapper.props.className, /sr-only/);
});

test('workspace transitions start in the layout phase and transfer focus once after completion', () => {
  const harness = createSessionHarness();
  harness.render();

  harness.paperTrading.view = 'dashboard';
  let view = harness.render();
  assert.equal(harness.timelines.length, 1, 'dashboard animation must exist before paint');
  assert.deepEqual(harness.focusCalls(), {
    triggerFocusCalls: 0,
    dashboardFocusCalls: 0,
    sessionHeadingFocusCalls: 0,
  });
  const dashboard = findElement(view, (element) => element.type === harness.PaperTradingDashboard);
  assert.equal(dashboard?.props.focusHeadingOnMount, false);
  assert.deepEqual(harness.timelines[0].from, { autoAlpha: 0, x: 18 });
  assert.equal(harness.timelines[0].to.duration, 0.26);

  harness.timelines[0].options.onComplete();
  assert.equal(harness.focusCalls().dashboardFocusCalls, 1);

  harness.paperTrading.view = 'session';
  view = harness.render();
  assert.equal(harness.timelines.length, 2);
  assert.deepEqual(harness.cleanupCalls(), { contextReverts: 1, timelineKills: 1 });
  assert.equal(harness.focusCalls().triggerFocusCalls, 0);
  harness.timelines[1].options.onComplete();
  assert.deepEqual(harness.focusCalls(), {
    triggerFocusCalls: 1,
    dashboardFocusCalls: 1,
    sessionHeadingFocusCalls: 0,
  });

  harness.unmount();
  assert.deepEqual(harness.cleanupCalls(), { contextReverts: 2, timelineKills: 2 });
});

test('a dashboard remount coordinates one entrance while a session remount stays still', () => {
  const dashboardHarness = createSessionHarness({ initialView: 'dashboard' });
  const dashboardView = dashboardHarness.render();
  const dashboard = findElement(
    dashboardView,
    (element) => element.type === dashboardHarness.PaperTradingDashboard
  );

  assert.equal(dashboard?.props.focusHeadingOnMount, false);
  assert.equal(dashboardHarness.timelines.length, 1, 'dashboard remount must animate before paint');
  assert.deepEqual(dashboardHarness.focusCalls(), {
    triggerFocusCalls: 0,
    dashboardFocusCalls: 0,
    sessionHeadingFocusCalls: 0,
  });

  dashboardHarness.timelines[0].options.onComplete();
  assert.equal(dashboardHarness.focusCalls().dashboardFocusCalls, 1);
  dashboardHarness.render();
  assert.equal(dashboardHarness.timelines.length, 1, 'stable dashboard must not animate again');
  assert.equal(dashboardHarness.focusCalls().dashboardFocusCalls, 1);

  const sessionHarness = createSessionHarness({ initialView: 'session' });
  sessionHarness.render();
  assert.equal(sessionHarness.timelines.length, 0, 'initial session must not animate');
  assert.deepEqual(sessionHarness.focusCalls(), {
    triggerFocusCalls: 0,
    dashboardFocusCalls: 0,
    sessionHeadingFocusCalls: 0,
  });
});

test('Strict Mode replay replaces the initial dashboard timeline before focusing once', () => {
  const harness = createSessionHarness({ initialView: 'dashboard' });
  harness.render();
  assert.equal(harness.timelines.length, 1);

  harness.strictModeReplayLayoutEffects();

  assert.equal(harness.timelines.length, 2, 'effect replay must create a replacement timeline');
  assert.equal(harness.timelines[0].killed, true);
  assert.equal(harness.timelines[1].killed, false);
  assert.equal(harness.timelines.filter((timeline) => !timeline.killed).length, 1);
  assert.deepEqual(harness.cleanupCalls(), { contextReverts: 1, timelineKills: 1 });
  assert.equal(harness.focusCalls().dashboardFocusCalls, 0);

  harness.timelines[1].options.onComplete();
  assert.equal(harness.focusCalls().dashboardFocusCalls, 1);
  assert.equal(harness.focusCalls().triggerFocusCalls, 0);
});

test('an interrupted dashboard entrance returns focus to the committed session trigger', () => {
  const harness = createSessionHarness({ initialView: 'session' });
  harness.render();

  harness.paperTrading.view = 'dashboard';
  harness.render();
  assert.equal(harness.timelines.length, 1);

  harness.paperTrading.view = 'session';
  harness.render();
  assert.equal(harness.timelines.length, 1, 'return to the committed view needs no animation');
  assert.equal(harness.timelines[0].killed, true);
  assert.deepEqual(harness.cleanupCalls(), { contextReverts: 1, timelineKills: 1 });
  assert.deepEqual(harness.focusCalls(), {
    triggerFocusCalls: 1,
    dashboardFocusCalls: 0,
    sessionHeadingFocusCalls: 0,
  });
  harness.render();
  assert.equal(harness.focusCalls().triggerFocusCalls, 1, 'stable session must not refocus');

  harness.paperTrading.view = 'dashboard';
  harness.render();
  assert.equal(harness.timelines.length, 2);
  assert.equal(harness.timelines.filter((timeline) => !timeline.killed).length, 1);
  harness.timelines[1].options.onComplete();
  assert.equal(harness.focusCalls().dashboardFocusCalls, 1);
});

test('an interrupted session return restores focus to the committed dashboard heading', () => {
  const harness = createSessionHarness({ initialView: 'dashboard' });
  harness.render();
  harness.timelines[0].options.onComplete();
  assert.equal(harness.focusCalls().dashboardFocusCalls, 1);

  harness.paperTrading.view = 'session';
  harness.render();
  assert.equal(harness.timelines.length, 2);
  assert.equal(harness.focusCalls().triggerFocusCalls, 0);

  harness.paperTrading.view = 'dashboard';
  harness.render();
  assert.equal(harness.timelines.length, 2, 'return to committed dashboard needs no animation');
  assert.equal(harness.timelines[1].killed, true);
  assert.equal(harness.focusCalls().dashboardFocusCalls, 2);
  assert.equal(harness.focusCalls().triggerFocusCalls, 0);

  harness.render();
  assert.equal(harness.focusCalls().dashboardFocusCalls, 2, 'stable dashboard must not refocus');
});

test('paper dashboard autofocus can be disabled without changing its standalone default', () => {
  function renderDashboard(props) {
    let focusCalls = 0;
    const react = {
      useEffect(effect) {
        effect();
      },
      useRef() {
        return { current: { focus: () => (focusCalls += 1) } };
      },
      useState(value) {
        return [value, () => undefined];
      },
    };
    const icon = () => null;
    const context = {
      readiness: 'ready',
      portfolio: { startingCashPaise: 10_000_000, holdings: [], fills: [] },
      draft: null,
      error: null,
      closeDashboard() {},
      confirmDraft() {},
      resetPortfolio() {},
    };
    const Dashboard = compile(
      'components/paper-trading/paper-trading-dashboard.tsx',
      new Map([
        ['react', react],
        ['react/jsx-runtime', jsxRuntime],
        ['lucide-react', new Proxy({}, { get: () => icon })],
        [
          '@radix-ui/react-dialog',
          {
            Root: 'div',
            Trigger: 'div',
            Portal: 'div',
            Overlay: 'div',
            Content: 'div',
            Title: 'div',
            Description: 'div',
            Close: 'div',
          },
        ],
        ['@/components/paper-trading/activity-ledger', { ActivityLedger: () => null }],
        ['@/components/paper-trading/holdings-ledger', { HoldingsLedger: () => null }],
        ['@/components/paper-trading/order-review', { OrderReview: () => null }],
        ['@/components/paper-trading/paper-trading-provider', { usePaperTrading: () => context }],
        ['@/components/paper-trading/portfolio-summary', { PortfolioSummary: () => null }],
      ])
    ).PaperTradingDashboard;
    Dashboard(props);
    return focusCalls;
  }

  assert.equal(renderDashboard({ focusHeadingOnMount: false }), 0);
  assert.equal(renderDashboard({}), 1);
});
