import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const frontendRoot = join(import.meta.dirname, '..');

function loadSessionRoom(Room) {
  const output = ts.transpileModule(
    readFileSync(join(frontendRoot, 'lib/session-room.ts'), 'utf8'),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }
  ).outputText;
  const compiledModule = { exports: {} };

  new Function('require', 'module', 'exports', output)(
    (specifier) => {
      if (specifier === 'livekit-client') return { Room };
      throw new Error(`Unexpected session-room dependency: ${specifier}`);
    },
    compiledModule,
    compiledModule.exports
  );

  return compiledModule.exports;
}

test('browser remounts recover the active LiveKit room instead of creating a ghost call', () => {
  const previousWindow = globalThis.window;
  let roomConstructions = 0;

  class Room {
    constructor() {
      roomConstructions += 1;
    }
  }

  globalThis.window = {};
  try {
    const firstModule = loadSessionRoom(Room);
    const activeRoom = firstModule.getPersistentSessionRoom();

    const refreshedModule = loadSessionRoom(Room);
    const recoveredRoom = refreshedModule.getPersistentSessionRoom();

    assert.equal(recoveredRoom, activeRoom);
    assert.equal(roomConstructions, 1);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
