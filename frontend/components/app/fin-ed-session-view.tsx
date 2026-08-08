'use client';

import { useLayoutEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ConnectionState } from 'livekit-client';
import { BookOpen, LayoutDashboard, Mic2, ShieldCheck } from 'lucide-react';
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
import { PaperTradingDashboard } from '@/components/paper-trading/paper-trading-dashboard';
import {
  type PaperTradingView,
  usePaperTrading,
} from '@/components/paper-trading/paper-trading-provider';
import { LEARNING_MODES, type LearningMode } from '@/lib/learning-modes';

const SESSION_EDUCATION_BOUNDARY =
  'Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP. For personalised decisions, consult a SEBI-registered investment adviser.';
const VOICE_LANGUAGES = 'English & Hindi';

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
}

export function FinEdSessionView({ appConfig, learningMode }: FinEdSessionViewProps) {
  const session = useSessionContext();
  const agent = useAgent();
  const { audioTrack } = useVoiceAssistant();
  const { messages } = useSessionMessages();
  const paperTrading = usePaperTrading();
  const shouldReduceMotion = useReducedMotion();
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(true);
  const paperTradingTriggerRef = useRef<HTMLButtonElement>(null);
  const previousPaperViewRef = useRef<PaperTradingView>(paperTrading.view);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const activeMode = LEARNING_MODES.find((mode) => mode.value === learningMode);
  const status = statusFor(session.connectionState, agent.state);
  const visualizerState: AgentState =
    shouldReduceMotion && agent.state === 'speaking' ? 'listening' : agent.state;

  useLayoutEffect(() => {
    const previousView = previousPaperViewRef.current;
    previousPaperViewRef.current = paperTrading.view;

    if (previousView === paperTrading.view) return;

    const moveFocus = () => {
      if (paperTrading.view === 'dashboard') {
        workspaceRef.current?.querySelector<HTMLElement>('h1')?.focus();
      } else {
        paperTradingTriggerRef.current?.focus();
      }
    };

    if (shouldReduceMotion) {
      moveFocus();
      return;
    }

    const workspace = workspaceRef.current;
    if (!workspace) return;

    let timeline: gsap.core.Timeline | undefined;
    const context = gsap.context(() => {
      timeline = gsap.timeline({ onComplete: moveFocus }).fromTo(
        workspace,
        { autoAlpha: 0, x: paperTrading.view === 'dashboard' ? 18 : -18 },
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
      timeline?.kill();
      context.revert();
    };
  }, [paperTrading.view, shouldReduceMotion]);

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
            {paperTrading.view === 'dashboard' && (
              <span className="rounded-[8px] border border-[var(--banknote-green)] bg-[var(--green-wash)] px-3 py-2 text-xs font-semibold text-[var(--banknote-green)]">
                Paper trading only
              </span>
            )}
            <button
              ref={paperTradingTriggerRef}
              type="button"
              aria-pressed={paperTrading.view === 'dashboard'}
              onClick={paperTrading.openDashboard}
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

      <div ref={workspaceRef} data-workspace-view={paperTrading.view}>
        {paperTrading.view === 'dashboard' ? (
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
                  <p className="font-display font-semibold">Conversation and sources</p>
                  <p className="mt-1 text-sm text-[var(--muted-ink)]">
                    Voice answers appear here with clickable source links.
                  </p>
                </div>
                <span className="font-data text-xs text-[var(--muted-ink)]">
                  {messages.length} {messages.length === 1 ? 'message' : 'messages'}
                </span>
              </div>

              <div hidden={!isTranscriptOpen} inert={!isTranscriptOpen} className="min-h-0 flex-1">
                <AgentChatTranscript
                  agentState={agent.state}
                  messages={messages}
                  className="min-h-0 flex-1"
                />
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
