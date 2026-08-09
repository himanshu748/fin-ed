export const VOICE_SESSION_STORAGE_KEY = 'fined.voice.sessions.v1';

const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_SESSIONS = 12;
const MAX_MESSAGES = 100;
const MAX_MESSAGE_LENGTH = 4_000;

export interface VoiceSessionStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface ArchivedVoiceMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: number;
}

export interface VoiceSessionArchive {
  sessionId: string;
  learningMode: string;
  startedAt: number;
  updatedAt: number;
  messages: ArchivedVoiceMessage[];
}

interface VoiceMessageLike {
  id?: unknown;
  type?: unknown;
  message?: unknown;
  timestamp?: unknown;
  from?: { isLocal?: unknown } | null;
}

export type LoadVoiceSessionsResult =
  | { status: 'ready'; sessions: VoiceSessionArchive[] }
  | { status: 'missing' | 'corrupt' | 'unavailable' };

export type ArchiveVoiceSessionResult =
  | { status: 'saved'; sessions: VoiceSessionArchive[] }
  | { status: 'corrupt' | 'unavailable' };

function finiteTimestamp(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function decodeMessage(value: unknown): ArchivedVoiceMessage {
  if (typeof value !== 'object' || value === null) throw new Error('Invalid message');
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.id !== 'string' ||
    candidate.id.length === 0 ||
    candidate.id.length > 200 ||
    (candidate.role !== 'user' && candidate.role !== 'assistant') ||
    typeof candidate.text !== 'string' ||
    candidate.text.length === 0 ||
    candidate.text.length > MAX_MESSAGE_LENGTH ||
    !finiteTimestamp(candidate.timestamp)
  ) {
    throw new Error('Invalid message');
  }
  return {
    id: candidate.id,
    role: candidate.role,
    text: candidate.text,
    timestamp: candidate.timestamp,
  };
}

function decodeSession(value: unknown): VoiceSessionArchive {
  if (typeof value !== 'object' || value === null) throw new Error('Invalid session');
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.sessionId !== 'string' ||
    !SESSION_ID_PATTERN.test(candidate.sessionId) ||
    typeof candidate.learningMode !== 'string' ||
    candidate.learningMode.length === 0 ||
    candidate.learningMode.length > 80 ||
    !finiteTimestamp(candidate.startedAt) ||
    !finiteTimestamp(candidate.updatedAt) ||
    !Array.isArray(candidate.messages)
  ) {
    throw new Error('Invalid session');
  }
  return {
    sessionId: candidate.sessionId.toLowerCase(),
    learningMode: candidate.learningMode,
    startedAt: candidate.startedAt,
    updatedAt: candidate.updatedAt,
    messages: candidate.messages.slice(-MAX_MESSAGES).map(decodeMessage),
  };
}

function newestFirst(sessions: VoiceSessionArchive[]): VoiceSessionArchive[] {
  return sessions
    .sort((left, right) => right.updatedAt - left.updatedAt || right.startedAt - left.startedAt)
    .slice(0, MAX_SESSIONS);
}

export function toArchivedVoiceMessages(messages: VoiceMessageLike[]): ArchivedVoiceMessage[] {
  const archived: ArchivedVoiceMessage[] = [];
  for (const message of messages) {
    if (
      typeof message.id !== 'string' ||
      message.id.length === 0 ||
      message.id.length > 200 ||
      typeof message.message !== 'string' ||
      !finiteTimestamp(message.timestamp)
    ) {
      continue;
    }
    const text = message.message.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (text.length === 0) continue;
    const role =
      message.type === 'userTranscript' ||
      (message.type !== 'agentTranscript' && message.from?.isLocal === true)
        ? 'user'
        : 'assistant';
    archived.push({ id: message.id, role, text, timestamp: message.timestamp });
  }
  return archived.slice(-MAX_MESSAGES);
}

export function loadVoiceSessions(
  storage: VoiceSessionStorage | null | undefined
): LoadVoiceSessionsResult {
  if (!storage || typeof storage.getItem !== 'function') return { status: 'unavailable' };
  let raw: string | null;
  try {
    raw = storage.getItem(VOICE_SESSION_STORAGE_KEY);
  } catch {
    return { status: 'unavailable' };
  }
  if (raw === null) return { status: 'missing' };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return { status: 'corrupt' };
    return { status: 'ready', sessions: newestFirst(parsed.map(decodeSession)) };
  } catch {
    return { status: 'corrupt' };
  }
}

export function archiveVoiceSession(
  storage: VoiceSessionStorage | null | undefined,
  session: VoiceSessionArchive
): ArchiveVoiceSessionResult {
  if (!storage || typeof storage.setItem !== 'function') return { status: 'unavailable' };
  let candidate: VoiceSessionArchive;
  try {
    candidate = decodeSession(session);
  } catch {
    return { status: 'corrupt' };
  }
  const loaded = loadVoiceSessions(storage);
  if (loaded.status === 'corrupt') return { status: 'corrupt' };
  if (loaded.status === 'unavailable') return { status: 'unavailable' };
  const existing = loaded.status === 'ready' ? loaded.sessions : [];
  const previous = existing.find((item) => item.sessionId === candidate.sessionId);
  const next = newestFirst([
    {
      ...candidate,
      startedAt: previous?.startedAt ?? candidate.startedAt,
    },
    ...existing.filter((item) => item.sessionId !== candidate.sessionId),
  ]);
  try {
    storage.setItem(VOICE_SESSION_STORAGE_KEY, JSON.stringify(next));
  } catch {
    return { status: 'unavailable' };
  }
  return { status: 'saved', sessions: next };
}

export function browserVoiceSessionStorage(): VoiceSessionStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}
