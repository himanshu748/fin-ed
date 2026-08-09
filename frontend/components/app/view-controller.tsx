'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useAgent, useSessionContext } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { FinEdSessionView } from '@/components/app/fin-ed-session-view';
import { WelcomeView } from '@/components/app/welcome-view';
import type { LearningMode } from '@/lib/learning-modes';

interface ViewControllerProps {
  appConfig: AppConfig;
  learningMode: LearningMode;
  onLearningModeChange: (mode: LearningMode) => void;
}

const MICROPHONE_PERMISSION_ERROR =
  'Microphone access is required for a voice call. Allow microphone access in your browser settings, then try connecting again.';
const VOICE_CONNECTION_ERROR = 'Voice connection failed. Check your network and try again.';
const CONNECTION_START_TIMEOUT_MS = 25_000;

async function startSessionWithTimeout(start: () => Promise<void>): Promise<void> {
  let timeout: ReturnType<typeof setTimeout> | undefined;

  try {
    await Promise.race([
      start(),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(
          () => reject(new Error('Voice connection timed out.')),
          CONNECTION_START_TIMEOUT_MS
        );
      }),
    ]);
  } finally {
    if (timeout !== undefined) clearTimeout(timeout);
  }
}

export function connectionErrorMessageFor(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  const message = error instanceof Error ? error.message : String(error ?? '');
  const permissionFailure =
    name === 'NotAllowedError' ||
    name === 'PermissionDeniedError' ||
    /(?:microphone|media device).*(?:permission|denied|not allowed)|(?:permission|denied|not allowed).*(?:microphone|media device)/i.test(
      message
    );

  return permissionFailure ? MICROPHONE_PERMISSION_ERROR : VOICE_CONNECTION_ERROR;
}

export function ViewController({
  appConfig,
  learningMode,
  onLearningModeChange,
}: ViewControllerProps) {
  const session = useSessionContext();
  const agent = useAgent();
  const shouldReduceMotion = useReducedMotion();
  const [isStarting, setIsStarting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const handlingFailure = useRef(false);

  useEffect(() => {
    if (agent.state !== 'failed' || !session.isConnected) {
      handlingFailure.current = false;
      return;
    }

    if (handlingFailure.current) return;
    handlingFailure.current = true;
    setConnectionError(VOICE_CONNECTION_ERROR);
    void session.end().catch(() => undefined);
  }, [agent.state, session]);

  const handleStart = async () => {
    if (isStarting) return;

    setConnectionError(null);
    setIsStarting(true);
    try {
      await startSessionWithTimeout(() => session.start());
    } catch (error) {
      setConnectionError(connectionErrorMessageFor(error));
      await session.end().catch(() => undefined);
    } finally {
      setIsStarting(false);
    }
  };

  const handleNewSession = async () => {
    if (isStarting) return;

    setConnectionError(null);
    setIsStarting(true);
    try {
      await session.end();
      await startSessionWithTimeout(() => session.start());
    } catch (error) {
      setConnectionError(connectionErrorMessageFor(error));
      await session.end().catch(() => undefined);
    } finally {
      setIsStarting(false);
    }
  };

  const motionProps = {
    initial: shouldReduceMotion ? false : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    exit: shouldReduceMotion ? undefined : { opacity: 0, y: -12 },
    transition: { duration: shouldReduceMotion ? 0 : 0.2, ease: 'easeOut' as const },
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      {!session.isConnected && (
        <motion.div key="welcome" {...motionProps}>
          {connectionError && (
            <div
              role="alert"
              className="fixed top-20 right-4 left-4 z-50 mx-auto max-w-2xl rounded-[12px] border border-[var(--risk-brick)] bg-[var(--risk-wash)] p-[18px] font-semibold text-[var(--risk-brick)] shadow-lg sm:left-auto sm:max-w-md"
            >
              {connectionError}
            </div>
          )}
          <WelcomeView
            learningMode={learningMode}
            onLearningModeChange={onLearningModeChange}
            onStartCall={handleStart}
            isConnecting={isStarting}
            connectionError={false}
          />
        </motion.div>
      )}
      {session.isConnected && (
        <motion.div key="session-view" {...motionProps}>
          <FinEdSessionView
            appConfig={appConfig}
            learningMode={learningMode}
            onNewSession={handleNewSession}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
