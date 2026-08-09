import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  module._compile(output, filename);
};

const {
  VOICE_SESSION_STORAGE_KEY,
  archiveVoiceSession,
  loadVoiceSessions,
  toArchivedVoiceMessages,
} = require('../lib/voice-session-history.ts');

function memoryStorage(entries = {}) {
  const values = new Map(Object.entries(entries));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

test('archives only safe transcript fields and removes participant identity', () => {
  const messages = toArchivedVoiceMessages([
    {
      id: 'user-1',
      type: 'userTranscript',
      message: 'What is an ETF?',
      timestamp: 1_754_637_000_000,
      from: { identity: 'voice_assistant_user_secret', isLocal: true },
    },
    {
      id: 'agent-1',
      type: 'agentTranscript',
      message: 'An ETF is a basket of assets.',
      timestamp: 1_754_637_001_000,
      from: { identity: 'agent-Nikhil', isLocal: false },
    },
  ]);

  assert.deepEqual(messages, [
    {
      id: 'user-1',
      role: 'user',
      text: 'What is an ETF?',
      timestamp: 1_754_637_000_000,
    },
    {
      id: 'agent-1',
      role: 'assistant',
      text: 'An ETF is a basket of assets.',
      timestamp: 1_754_637_001_000,
    },
  ]);
  assert.doesNotMatch(JSON.stringify(messages), /voice_assistant_user_secret|agent-Nikhil/);
});

test('saves browser sessions newest first and updates an existing session in place', () => {
  const storage = memoryStorage();
  const first = {
    sessionId: '550e8400-e29b-41d4-a716-446655440000',
    learningMode: 'general',
    startedAt: 1_754_637_000_000,
    updatedAt: 1_754_637_001_000,
    messages: [
      {
        id: 'first-message',
        role: 'user',
        text: 'What is an ETF?',
        timestamp: 1_754_637_000_000,
      },
    ],
  };
  const second = {
    sessionId: '67e55044-10b1-426f-9247-bb680e5fe0c8',
    learningMode: 'stocks',
    startedAt: 1_754_638_000_000,
    updatedAt: 1_754_638_001_000,
    messages: [
      {
        id: 'second-message',
        role: 'user',
        text: 'What is a stock?',
        timestamp: 1_754_638_000_000,
      },
    ],
  };

  assert.equal(archiveVoiceSession(storage, first).status, 'saved');
  assert.equal(archiveVoiceSession(storage, second).status, 'saved');
  assert.equal(
    archiveVoiceSession(storage, {
      ...first,
      updatedAt: 1_754_639_000_000,
      messages: [
        { id: 'm1', role: 'user', text: 'Updated question', timestamp: 1_754_639_000_000 },
      ],
    }).status,
    'saved'
  );

  const result = loadVoiceSessions(storage);
  assert.equal(result.status, 'ready');
  assert.deepEqual(
    result.sessions.map((session) => session.sessionId),
    [first.sessionId, second.sessionId]
  );
  assert.equal(result.sessions[0].messages[0].text, 'Updated question');
});

test('ignores empty snapshots so a disconnect cannot erase a recorded transcript', () => {
  const storage = memoryStorage();
  const sessionId = '550e8400-e29b-41d4-a716-446655440000';
  const recorded = {
    sessionId,
    learningMode: 'general',
    startedAt: 1_754_637_000_000,
    updatedAt: 1_754_637_001_000,
    messages: [
      {
        id: 'm1',
        role: 'user',
        text: 'What is an ETF?',
        timestamp: 1_754_637_000_000,
      },
    ],
  };

  assert.equal(archiveVoiceSession(storage, recorded).status, 'saved');
  assert.equal(
    archiveVoiceSession(storage, {
      ...recorded,
      updatedAt: 1_754_638_000_000,
      messages: [],
    }).status,
    'empty'
  );

  const result = loadVoiceSessions(storage);
  assert.equal(result.status, 'ready');
  assert.equal(result.sessions.length, 1);
  assert.equal(result.sessions[0].messages[0].text, 'What is an ETF?');
});

test('hides legacy connection attempts that have no transcript messages', () => {
  const storage = memoryStorage({
    [VOICE_SESSION_STORAGE_KEY]: JSON.stringify([
      {
        sessionId: '550e8400-e29b-41d4-a716-446655440000',
        learningMode: 'general',
        startedAt: 1_754_637_000_000,
        updatedAt: 1_754_637_001_000,
        messages: [],
      },
      {
        sessionId: '67e55044-10b1-426f-9247-bb680e5fe0c8',
        learningMode: 'stocks',
        startedAt: 1_754_638_000_000,
        updatedAt: 1_754_638_001_000,
        messages: [
          {
            id: 'm1',
            role: 'assistant',
            text: 'An ETF is a basket of assets.',
            timestamp: 1_754_638_001_000,
          },
        ],
      },
    ]),
  });

  const result = loadVoiceSessions(storage);
  assert.equal(result.status, 'ready');
  assert.deepEqual(
    result.sessions.map((session) => session.sessionId),
    ['67e55044-10b1-426f-9247-bb680e5fe0c8']
  );
});

test('fails closed for corrupt history and unavailable browser storage', () => {
  assert.deepEqual(loadVoiceSessions(memoryStorage({ [VOICE_SESSION_STORAGE_KEY]: '{' })), {
    status: 'corrupt',
  });
  assert.deepEqual(
    loadVoiceSessions({
      getItem() {
        throw new Error('blocked');
      },
      setItem() {
        throw new Error('blocked');
      },
    }),
    { status: 'unavailable' }
  );
});

test('bounds local history to twelve sessions and one hundred messages per session', () => {
  const storage = memoryStorage();
  for (let index = 0; index < 14; index += 1) {
    const suffix = index.toString(16).padStart(12, '0');
    archiveVoiceSession(storage, {
      sessionId: `550e8400-e29b-41d4-a716-${suffix}`,
      learningMode: 'general',
      startedAt: index,
      updatedAt: index,
      messages: Array.from({ length: 105 }, (_, messageIndex) => ({
        id: `m-${messageIndex}`,
        role: messageIndex % 2 === 0 ? 'user' : 'assistant',
        text: `Message ${messageIndex}`,
        timestamp: messageIndex,
      })),
    });
  }

  const result = loadVoiceSessions(storage);
  assert.equal(result.status, 'ready');
  assert.equal(result.sessions.length, 12);
  assert.equal(result.sessions[0].messages.length, 100);
  assert.equal(result.sessions[0].sessionId, '550e8400-e29b-41d4-a716-00000000000d');
});
