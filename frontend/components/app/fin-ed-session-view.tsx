'use client';

import { useState } from 'react';
import { ConnectionState } from 'livekit-client';
import { BookOpen, LockKeyhole, Mic2, ShieldCheck } from 'lucide-react';
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
import { LEARNING_MODES, type LearningMode } from '@/lib/learning-modes';

const SESSION_EDUCATION_BOUNDARY =
  'Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP.';

function statusFor(connectionState: ConnectionState, agentState: AgentState) {
  if (
    connectionState === ConnectionState.Reconnecting ||
    connectionState === ConnectionState.SignalReconnecting
  ) {
    return { label: 'Reconnecting securely', tone: 'warning' as const };
  }

  switch (agentState) {
    case 'listening':
      return { label: 'Listening for your question', tone: 'connected' as const };
    case 'thinking':
      return { label: 'Working through the concept', tone: 'active' as const };
    case 'speaking':
      return { label: 'Explaining in English or Hindi', tone: 'active' as const };
    case 'failed':
      return { label: 'Voice agent unavailable', tone: 'failed' as const };
    case 'initializing':
    case 'pre-connect-buffering':
    case 'connecting':
      return { label: 'Connecting to FinEd Saathi', tone: 'warning' as const };
    case 'idle':
      return { label: 'Ready for a market question', tone: 'connected' as const };
    default:
      return { label: 'Session disconnected', tone: 'failed' as const };
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
  const shouldReduceMotion = useReducedMotion();
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(true);
  const activeMode = LEARNING_MODES.find((mode) => mode.value === learningMode);
  const status = statusFor(session.connectionState, agent.state);
  const visualizerState: AgentState =
    shouldReduceMotion && agent.state === 'speaking' ? 'listening' : agent.state;

  return (
    <div className="min-h-svh bg-[var(--paper)] text-[var(--ledger-ink)]">
      <header className="border-b border-[var(--ledger-rule)] bg-[rgb(246_242_232/0.94)] backdrop-blur-md">
        <div className="section-shell flex min-h-18 flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-[10px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] text-[var(--ledger-blue)]">
              <BookOpen aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="font-display truncate font-bold">FinEd Saathi</p>
              <p className="font-data truncate text-xs text-[var(--muted-ink)]">
                {activeMode?.label ?? 'Ask Anything'} mode
              </p>
            </div>
          </div>

          <div
            role="status"
            aria-live="polite"
            className="flex min-h-10 items-center gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] px-3 text-sm"
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
            <span className="font-semibold">{status.label}</span>
          </div>
        </div>
      </header>

      <main className="section-shell grid min-h-[calc(100svh-4.5rem)] gap-5 py-5 lg:grid-cols-[minmax(16rem,0.72fr)_minmax(0,1.28fr)] lg:py-8">
        <aside className="flex flex-col rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <p className="font-data text-xs tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
              Live voice session
            </p>
            <ShieldCheck aria-hidden="true" className="size-5 text-[var(--banknote-green)]" />
          </div>
          <h1 className="font-display mt-4 text-2xl leading-tight font-bold">
            Ask one market concept at a time.
          </h1>
          <p className="mt-3 leading-7 text-[var(--muted-ink)]">
            Nikhil answers in either English or Hindi using Murf Falcon 2. Languages are not mixed.
          </p>

          <div className="my-8 grid min-h-44 place-items-center rounded-[12px] border border-[var(--soft-rule)] bg-[var(--paper)] p-5">
            <AgentAudioVisualizerBar
              aria-label={`Voice activity: ${status.label}`}
              size="sm"
              state={visualizerState}
              color={appConfig.audioVisualizerColor ?? '#174EA6'}
              barCount={appConfig.audioVisualizerBarCount ?? 7}
              audioTrack={audioTrack}
              className="w-full"
            >
              <div className="min-h-2 w-2 rounded-[2px] bg-current/15 transition-[height,background-color] duration-150 ease-out data-[lk-highlighted=true]:bg-current motion-reduce:transition-none" />
            </AgentAudioVisualizerBar>
          </div>

          <div className="rounded-[12px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] p-4">
            <div className="flex items-center gap-2 font-semibold text-[var(--ledger-blue)]">
              <LockKeyhole aria-hidden="true" className="size-4" />
              <span>{activeMode?.label ?? 'Ask Anything'}</span>
            </div>
            <p className="mt-2 text-sm text-[var(--muted-ink)]">Mode locked for this call</p>
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

          {isTranscriptOpen ? (
            <AgentChatTranscript
              agentState={agent.state}
              messages={messages}
              className="min-h-0 flex-1"
            />
          ) : (
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
            className="mt-3 rounded-[12px] border-[var(--ledger-rule)] bg-[var(--paper)] shadow-none drop-shadow-none [&_button]:min-h-11 [&_button]:min-w-11"
          />
        </section>
      </main>
    </div>
  );
}
