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

function loadViewController({ agentState, isConnected, startError }) {
  const stateWrites = [];
  let stateIndex = 0;
  let endCalls = 0;
  const session = {
    isConnected,
    start: async () => {
      if (startError) throw startError;
    },
    end: async () => {
      endCalls += 1;
    },
  };
  const react = {
    useEffect(effect) {
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
    ['@/components/app/fin-ed-session-view', { FinEdSessionView: () => null }],
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

  return { endCalls, stateWrites, view, exports: compiledModule.exports };
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
