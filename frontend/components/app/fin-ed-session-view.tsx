'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ConnectionState } from 'livekit-client';
import {
  BookOpen,
  Check,
  Copy,
  History,
  LayoutDashboard,
  LifeBuoy,
  Mic2,
  Plus,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useReducedMotion } from 'motion/react';
import {
  type AgentState,
  useAgent,
  useSessionContext,
  useSessionMessages,
  useVoiceAssistant,
} from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentAudioVisualizerBar } from '@/components/agents-ui/agent-audio-visualizer-bar';
import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';
import { AgentControlBar } from '@/components/agents-ui/agent-control-bar';
import { HumanHelpDashboard } from '@/components/human-help/escalation-dashboard';
import { useHumanHelp } from '@/components/human-help/escalation-provider';
import { PaperTradingDashboard } from '@/components/paper-trading/paper-trading-dashboard';
import {
  type PaperTradingView,
  usePaperTrading,
} from '@/components/paper-trading/paper-trading-provider';
import { LEARNING_MODES, type LearningMode } from '@/lib/learning-modes';
import {
  type VoiceSessionArchive,
  archiveVoiceSession,
  browserVoiceSessionStorage,
  loadVoiceSessions,
  toArchivedVoiceMessages,
} from '@/lib/voice-session-history';

const SESSION_EDUCATION_BOUNDARY =
  'Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP. For personalised decisions, consult a SEBI-registered investment adviser.';
const VOICE_LANGUAGES = 'English & Hindi';
const SESSION_ROOM_PREFIX = 'voice_assistant_room_';
const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
type WorkspaceView = PaperTradingView | 'human-help';

export function sessionIdFromRoomName(roomName: string): string | null {
  if (!roomName.startsWith(SESSION_ROOM_PREFIX)) return null;
  const sessionId = roomName.slice(SESSION_ROOM_PREFIX.length);
  return SESSION_ID_PATTERN.test(sessionId) ? sessionId.toLowerCase() : null;
}

function statusFor(connectionState: ConnectionState, agentState: AgentState) {
  if (
    connectionState === ConnectionState.Reconnecting ||
    connectionState === ConnectionState.SignalReconnecting
  ) {
    return { label: 'Connecting', detail: 'Reconnecting securely', tone: 'warning' as const };
  }

  if (connectionState === ConnectionState.Disconnected) {
    return { label: 'Ended', detail: 'Session disconnected', tone: 'failed' as const };
  }

  switch (agentState) {
    case 'listening':
      return { label: 'Listening', detail: 'Ready for your question', tone: 'connected' as const };
    case 'thinking':
      return { label: 'Thinking', detail: 'Working through the concept', tone: 'active' as const };
    case 'speaking':
      return {
        label: 'Speaking',
        detail: 'Explaining in your language style',
        tone: 'active' as const,
      };
    case 'failed':
      return { label: 'Ended', detail: 'Voice agent unavailable', tone: 'failed' as const };
    case 'initializing':
    case 'pre-connect-buffering':
    case 'connecting':
      return {
        label: 'Connecting',
        detail: 'Connecting to FinEd Saathi',
        tone: 'warning' as const,
      };
    case 'idle':
      return { label: 'Ready', detail: 'Ready for a market question', tone: 'connected' as const };
    default:
      return { label: 'Ended', detail: 'Session disconnected', tone: 'failed' as const };
  }
}

interface FinEdSessionViewProps {
  appConfig: AppConfig;
  learningMode: LearningMode;
  onNewSession?: () => Promise<void>;
}

export function FinEdSessionView({ appConfig, learningMode, onNewSession }: FinEdSessionViewProps) {
  const session = useSessionContext();
  const agent = useAgent();
  const { audioTrack } = useVoiceAssistant();
  const { messages } = useSessionMessages();
  const paperTrading = usePaperTrading();
  const humanHelp = useHumanHelp();
  const shouldReduceMotion = useReducedMotion();
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(true);
  const [isSessionIdCopied, setIsSessionIdCopied] = useState(false);
  const [isSessionListOpen, setIsSessionListOpen] = useState(false);
  const [savedSessions, setSavedSessions] = useState<VoiceSessionArchive[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const paperTradingTriggerRef = useRef<HTMLButtonElement>(null);
  const committedPaperViewRef = useRef<{
    view: WorkspaceView | null;
    interrupted: boolean;
  }>({ view: null, interrupted: false });
  const workspaceRef = useRef<HTMLDivElement>(null);
  const humanHelpTriggerRef = useRef<HTMLButtonElement>(null);
  const lastWorkspaceTriggerRef = useRef<HTMLButtonElement | null>(null);
  const activeMode = LEARNING_MODES.find((mode) => mode.value === learningMode);
  const status = statusFor(session.connectionState, agent.state);
  const sessionId = sessionIdFromRoomName(session.room.name);
  const selectedSession = savedSessions.find(
    (savedSession) =>
      savedSession.sessionId === selectedSessionId && savedSession.sessionId !== sessionId
  );
  const displayedMessageCount = selectedSession?.messages.length ?? messages.length;
  const visualizerState: AgentState =
    shouldReduceMotion && agent.state === 'speaking' ? 'listening' : agent.state;
  const workspaceView: WorkspaceView = humanHelp.isOpen ? 'human-help' : paperTrading.view;

  const copySessionId = async () => {
    if (sessionId === null || navigator.clipboard === undefined) return;
    try {
      await navigator.clipboard.writeText(sessionId);
      setIsSessionIdCopied(true);
    } catch {
      setIsSessionIdCopied(false);
    }
  };

  useEffect(() => {
    const result = loadVoiceSessions(browserVoiceSessionStorage());
    if (result.status === 'ready') setSavedSessions(result.sessions);
  }, [sessionId]);

  useEffect(() => {
    if (sessionId === null) return;
    const archivedMessages = toArchivedVoiceMessages(messages);
    const now = Date.now();
    const result = archiveVoiceSession(browserVoiceSessionStorage(), {
      sessionId,
      learningMode,
      startedAt: archivedMessages[0]?.timestamp ?? now,
      updatedAt: archivedMessages.at(-1)?.timestamp ?? now,
      messages: archivedMessages,
    });
    if (result.status === 'saved') setSavedSessions(result.sessions);
  }, [learningMode, messages, sessionId]);

  useLayoutEffect(() => {
    const targetView = workspaceView;
    const transitionState = committedPaperViewRef.current;
    const committedView = transitionState.view;

    const moveFocus = (view: WorkspaceView) => {
      if (view !== 'session') {
        workspaceRef.current?.querySelector<HTMLElement>('h1')?.focus();
      } else {
        if (lastWorkspaceTriggerRef.current) lastWorkspaceTriggerRef.current.focus();
        else paperTradingTriggerRef.current?.focus();
      }
    };

    if (committedView === targetView) {
      if (transitionState.interrupted) {
        transitionState.interrupted = false;
        moveFocus(targetView);
      }
      return;
    }

    if (committedView === null && targetView === 'session') {
      transitionState.view = targetView;
      transitionState.interrupted = false;
      return;
    }

    if (shouldReduceMotion) {
      transitionState.view = targetView;
      transitionState.interrupted = false;
      moveFocus(targetView);
      return;
    }

    const workspace = workspaceRef.current;
    if (!workspace) return;

    transitionState.interrupted = false;
    let didComplete = false;
    let timeline: gsap.core.Timeline | undefined;
    const context = gsap.context(() => {
      timeline = gsap
        .timeline({
          onComplete: () => {
            didComplete = true;
            transitionState.view = targetView;
            transitionState.interrupted = false;
            moveFocus(targetView);
          },
        })
        .fromTo(
          workspace,
          { autoAlpha: 0, x: targetView === 'dashboard' ? 18 : -18 },
          {
            autoAlpha: 1,
            x: 0,
            duration: 0.26,
            ease: 'power2.out',
            clearProps: 'transform,opacity,visibility',
          }
        );
    }, workspace);

    return () => {
      if (!didComplete) transitionState.interrupted = true;
      timeline?.kill();
      context.revert();
    };
  }, [shouldReduceMotion, workspaceView]);

  return (
    <div className="min-h-svh bg-[var(--paper)] text-[var(--ledger-ink)]">
      <header className="border-b border-[var(--ledger-rule)] bg-[rgb(246_242_232/0.94)] backdrop-blur-md">
        <div className="section-shell flex min-h-18 flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="relative grid size-10 shrink-0 place-items-center rounded-[10px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] text-[var(--ledger-blue)]">
              <BookOpen aria-hidden="true" className="size-5 -translate-x-1" />
              <Mic2
                aria-hidden="true"
                className="absolute right-1 bottom-1 size-3.5 text-[var(--banknote-green)]"
              />
            </span>
            <div className="min-w-0">
              <p className="font-display truncate font-bold">FinEd Saathi</p>
              <p className="font-data truncate text-xs text-[var(--muted-ink)]">
                {activeMode?.label ?? 'Ask Anything'} mode
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="hidden border-r border-[var(--ledger-rule)] pr-3 text-right md:block">
              <p className="font-display text-sm font-bold">Nikhil</p>
              <p className="font-data text-[11px] text-[var(--muted-ink)]">
                Murf Falcon 2 · India voice · {VOICE_LANGUAGES}
              </p>
            </div>
            <div className="flex min-h-11 min-w-0 items-center gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] px-2.5 py-1.5">
              <div className="min-w-0">
                <p className="font-data text-[10px] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                  Session ID
                </p>
                <code
                  data-session-id={sessionId ?? undefined}
                  title={sessionId ?? 'Session ID pending'}
                  className="font-data block max-w-28 truncate text-[11px] text-[var(--ledger-ink)] sm:max-w-44"
                >
                  {sessionId ?? 'Pending'}
                </code>
              </div>
              <button
                type="button"
                aria-label="Copy session ID"
                disabled={sessionId === null}
                onClick={copySessionId}
                className="flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-[8px] text-xs font-semibold text-[var(--ledger-blue)] transition-colors hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-1 focus-visible:outline-[var(--ledger-blue)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSessionIdCopied ? (
                  <Check aria-hidden="true" className="size-4" />
                ) : (
                  <Copy aria-hidden="true" className="size-4" />
                )}
                <span className="hidden xl:inline">{isSessionIdCopied ? 'Copied' : 'Copy'}</span>
                <span className="sr-only xl:hidden">{isSessionIdCopied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <button
              type="button"
              aria-label={isSessionListOpen ? 'Close sessions' : 'Open sessions'}
              aria-expanded={isSessionListOpen}
              onClick={() => setIsSessionListOpen((isOpen) => !isOpen)}
              className="flex min-h-11 min-w-11 items-center gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] px-3 text-sm font-semibold transition-colors hover:border-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
            >
              <History aria-hidden="true" className="size-5 text-[var(--ledger-blue)]" />
              <span className="hidden sm:inline">Sessions</span>
            </button>
            {paperTrading.view === 'dashboard' && (
              <span className="rounded-[8px] border border-[var(--banknote-green)] bg-[var(--green-wash)] px-3 py-2 text-xs font-semibold text-[var(--banknote-green)]">
                Paper trading only
              </span>
            )}
            <button
              ref={humanHelpTriggerRef}
              type="button"
              aria-pressed={humanHelp.isOpen}
              onClick={() => {
                lastWorkspaceTriggerRef.current = humanHelpTriggerRef.current;
                humanHelp.open();
              }}
              className="flex min-h-11 min-w-11 items-center gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] px-3 text-sm font-semibold transition-colors hover:border-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
            >
              <LifeBuoy aria-hidden="true" className="size-5 text-[var(--ledger-blue)]" />
              <span>Human help</span>
              {humanHelp.requests.length > 0 && (
                <span className="font-data rounded-[6px] bg-[var(--ledger-blue)] px-1.5 py-0.5 text-[10px] text-white">
                  {humanHelp.requests.length}
                </span>
              )}
            </button>
            <button
              ref={paperTradingTriggerRef}
              type="button"
              aria-pressed={paperTrading.view === 'dashboard'}
              onClick={() => {
                lastWorkspaceTriggerRef.current = paperTradingTriggerRef.current;
                humanHelp.close();
                paperTrading.openDashboard();
              }}
              className="flex min-h-11 min-w-11 items-center gap-2 rounded-[10px] border border-[var(--ledger-blue)] px-3 text-sm font-semibold text-[var(--ledger-blue)] transition-colors hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
            >
              <LayoutDashboard aria-hidden="true" className="size-5" />
              Paper trading
            </button>
            <div
              role="status"
              aria-live="polite"
              className="flex min-h-11 items-center gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] px-3 text-sm"
            >
              <span
                aria-hidden="true"
                className={`size-2 rounded-[2px] ${
                  status.tone === 'connected'
                    ? 'bg-[var(--banknote-green)]'
                    : status.tone === 'failed'
                      ? 'bg-[var(--risk-brick)]'
                      : 'bg-[var(--ledger-blue)]'
                }`}
              />
              <span>
                <span className="font-semibold">{status.label}</span>
                <span className="sr-only">: {status.detail}</span>
              </span>
            </div>
          </div>
        </div>
        <div className="section-shell border-t border-[var(--soft-rule)] py-2 text-xs text-[var(--muted-ink)] md:hidden">
          <span className="font-semibold text-[var(--ledger-ink)]">Nikhil</span> · Murf Falcon 2 ·
          India voice · {VOICE_LANGUAGES}
        </div>
      </header>

      {isSessionListOpen && (
        <section
          aria-label="Voice sessions"
          className="border-b border-[var(--ledger-rule)] bg-[var(--surface)]"
        >
          <div className="section-shell py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-display font-bold">Your voice sessions</p>
                <p className="mt-1 text-sm text-[var(--muted-ink)]">
                  Transcripts are saved only in this browser. Ended sessions are read-only.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {onNewSession && (
                  <button
                    type="button"
                    onClick={async () => {
                      setIsSessionListOpen(false);
                      setSelectedSessionId(null);
                      await onNewSession();
                    }}
                    className="flex min-h-11 items-center gap-2 rounded-[10px] bg-[var(--ledger-blue)] px-4 text-sm font-semibold text-white transition-[filter] hover:brightness-90 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
                  >
                    <Plus aria-hidden="true" className="size-4" />
                    New session
                  </button>
                )}
                <button
                  type="button"
                  aria-label="Close sessions"
                  onClick={() => setIsSessionListOpen(false)}
                  className="grid min-h-11 min-w-11 place-items-center rounded-[10px] border border-[var(--ledger-rule)] hover:bg-[var(--paper)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
                >
                  <X aria-hidden="true" className="size-5" />
                </button>
              </div>
            </div>

            <div className="mt-4 flex gap-2 overflow-x-auto pb-1" role="list">
              <button
                type="button"
                role="listitem"
                aria-current={selectedSession === undefined ? 'page' : undefined}
                onClick={() => {
                  setSelectedSessionId(null);
                  setIsSessionListOpen(false);
                }}
                className="min-w-56 rounded-[10px] border border-[var(--banknote-green)] bg-[var(--green-wash)] p-3 text-left focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
              >
                <span className="font-data text-[10px] tracking-[0.08em] text-[var(--banknote-green)] uppercase">
                  Live now
                </span>
                <span className="font-data mt-1 block text-[10px] text-[var(--muted-ink)] uppercase">
                  {messages.length} {messages.length === 1 ? 'message' : 'messages'}
                </span>
                <code className="font-data mt-1 block truncate text-xs">
                  {sessionId ?? 'Session pending'}
                </code>
              </button>
              {savedSessions
                .filter((savedSession) => savedSession.sessionId !== sessionId)
                .map((savedSession) => (
                  <button
                    type="button"
                    role="listitem"
                    key={savedSession.sessionId}
                    aria-current={
                      selectedSession?.sessionId === savedSession.sessionId ? 'page' : undefined
                    }
                    onClick={() => {
                      setSelectedSessionId(savedSession.sessionId);
                      setIsSessionListOpen(false);
                    }}
                    className="min-w-56 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--paper)] p-3 text-left transition-colors hover:border-[var(--ledger-blue)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
                  >
                    <span className="font-data text-[10px] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                      {savedSession.messages.length} messages
                    </span>
                    <code className="font-data mt-1 block truncate text-xs">
                      {savedSession.sessionId}
                    </code>
                    <span className="mt-1 block text-xs text-[var(--muted-ink)]">
                      {new Date(savedSession.updatedAt).toLocaleString('en-IN', {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </span>
                  </button>
                ))}
            </div>
          </div>
        </section>
      )}

      <div ref={workspaceRef} data-workspace-view={workspaceView}>
        {workspaceView === 'human-help' ? (
          <HumanHelpDashboard />
        ) : paperTrading.view === 'dashboard' ? (
          <PaperTradingDashboard focusHeadingOnMount={false} />
        ) : (
          <main className="section-shell grid min-h-[calc(100svh-11rem)] gap-5 py-5 lg:grid-cols-[minmax(16rem,0.72fr)_minmax(0,1.28fr)] lg:py-8">
            <aside className="flex flex-col rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] sm:p-6">
              <div className="flex items-center justify-between gap-3">
                <p className="font-data text-xs tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
                  Live voice session
                </p>
                <ShieldCheck aria-hidden="true" className="size-5 text-[var(--banknote-green)]" />
              </div>
              <h1
                tabIndex={-1}
                className="font-display mt-4 text-2xl leading-tight font-bold focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-[var(--ledger-blue)]"
              >
                Ask one market concept at a time.
              </h1>
              <p className="mt-3 leading-7 text-[var(--muted-ink)]">
                Nikhil answers in English, Hindi, or both using Murf Falcon 2.
                <br /> He matches the language style you use.
              </p>

              <div className="my-8 rounded-[12px] border border-[var(--soft-rule)] bg-[var(--paper)] p-5">
                <p className="font-data text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                  Voice state
                </p>
                <p className="font-display mt-3 text-xl font-semibold">{status.label}</p>
                <p className="mt-2 text-sm text-[var(--muted-ink)]">{status.detail}</p>
              </div>

              <div className="rounded-[12px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] p-4">
                <div className="flex items-center gap-2 font-semibold text-[var(--ledger-blue)]">
                  <BookOpen aria-hidden="true" className="size-4" />
                  <span>{activeMode?.label ?? 'Ask Anything'}</span>
                </div>
                <p className="mt-2 text-sm text-[var(--muted-ink)]">
                  Learning focus for this call. End the call to choose another topic.
                </p>
              </div>

              <p className="mt-5 text-sm leading-6 text-[var(--muted-ink)]">
                {SESSION_EDUCATION_BOUNDARY}
              </p>
            </aside>

            <section className="flex min-h-[34rem] min-w-0 flex-col rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-3 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--soft-rule)] px-1 pb-4">
                <div>
                  <p className="font-display font-semibold">
                    {selectedSession ? 'Read-only browser history' : 'Conversation and sources'}
                  </p>
                  <p className="mt-1 text-sm text-[var(--muted-ink)]">
                    {selectedSession
                      ? `Session ${selectedSession.sessionId}`
                      : 'Voice answers appear here with clickable source links.'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {selectedSession && (
                    <button
                      type="button"
                      onClick={() => setSelectedSessionId(null)}
                      className="min-h-11 rounded-[9px] border border-[var(--ledger-blue)] px-3 text-sm font-semibold text-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
                    >
                      Back to live
                    </button>
                  )}
                  <span className="font-data text-xs text-[var(--muted-ink)]">
                    {displayedMessageCount} {displayedMessageCount === 1 ? 'message' : 'messages'}
                  </span>
                </div>
              </div>

              <div hidden={!isTranscriptOpen} inert={!isTranscriptOpen} className="min-h-0 flex-1">
                {selectedSession ? (
                  <ol className="flex max-h-[34rem] min-h-72 flex-col gap-4 overflow-y-auto px-1 py-5">
                    {selectedSession.messages.length === 0 ? (
                      <li className="grid min-h-64 place-items-center text-center text-sm text-[var(--muted-ink)]">
                        No transcript was recorded for this session.
                      </li>
                    ) : (
                      selectedSession.messages.map((message) => (
                        <li
                          key={message.id}
                          className={`max-w-[88%] rounded-[12px] border p-4 ${
                            message.role === 'user'
                              ? 'ml-auto border-[var(--ledger-blue)] bg-[var(--blue-wash)]'
                              : 'mr-auto border-[var(--ledger-rule)] bg-[var(--paper)]'
                          }`}
                        >
                          <p className="font-data text-[10px] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                            {message.role === 'user' ? 'You' : 'Nikhil'}
                          </p>
                          <p className="mt-2 text-sm leading-6 break-words whitespace-pre-wrap">
                            {message.text}
                          </p>
                        </li>
                      ))
                    )}
                  </ol>
                ) : (
                  <AgentChatTranscript
                    agentState={agent.state}
                    messages={messages}
                    className="min-h-0 flex-1"
                  />
                )}
              </div>
              {!isTranscriptOpen && (
                <div className="grid flex-1 place-items-center p-8 text-center">
                  <div>
                    <Mic2 aria-hidden="true" className="mx-auto size-8 text-[var(--ledger-blue)]" />
                    <p className="font-display mt-4 font-semibold">Transcript hidden</p>
                    <p className="mt-2 text-sm text-[var(--muted-ink)]">
                      Use the chat control below to show it again.
                    </p>
                  </div>
                </div>
              )}
            </section>
          </main>
        )}
      </div>

      <div className="sticky bottom-0 z-40 border-t border-[var(--ledger-rule)] bg-[rgb(246_242_232/0.96)] px-4 py-3 backdrop-blur-md">
        <div className="section-shell flex flex-col gap-2 rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-2 sm:flex-row sm:items-center">
          <div className="flex min-w-32 items-center gap-3 px-2 text-[var(--ledger-blue)]">
            <AgentAudioVisualizerBar
              aria-label={`Voice activity: ${status.label}. ${status.detail}`}
              size="sm"
              state={visualizerState}
              color={appConfig.audioVisualizerColor ?? '#174EA6'}
              barCount={appConfig.audioVisualizerBarCount ?? 7}
              audioTrack={audioTrack}
              className="h-8 min-w-24 flex-1"
            >
              <div className="min-h-2 w-2 rounded-[2px] bg-current/15 transition-[height,background-color] duration-150 ease-out data-[lk-highlighted=true]:bg-current motion-reduce:transition-none" />
            </AgentAudioVisualizerBar>
            <span className="font-data text-xs font-semibold">{status.label}</span>
          </div>
          <AgentControlBar
            variant="outline"
            isConnected={session.isConnected}
            isChatOpen={isTranscriptOpen}
            onIsChatOpenChange={setIsTranscriptOpen}
            controls={{
              leave: true,
              microphone: true,
              chat: true,
              camera: false,
              screenShare: false,
            }}
            className="min-w-0 flex-1 border-0 bg-transparent shadow-none drop-shadow-none [&_button]:min-h-11 [&_button]:min-w-11"
          />
        </div>
      </div>
    </div>
  );
}
