import * as jsxRuntime from 'react/jsx-runtime';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const frontendRoot = join(import.meta.dirname, '..');

function loadViewController({ agentState, isConnected }) {
  const stateWrites = [];
  let stateIndex = 0;
  let endCalls = 0;
  const session = {
    isConnected,
    start: async () => undefined,
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

  compiledModule.exports.ViewController({
    appConfig: {},
    learningMode: 'general',
    onLearningModeChange: () => undefined,
  });

  return { endCalls, stateWrites };
}

test('a failed agent state after the room disconnected is not reported as a connection failure', () => {
  const result = loadViewController({ agentState: 'failed', isConnected: false });

  assert.equal(result.endCalls, 0);
  assert.deepEqual(result.stateWrites, []);
});
