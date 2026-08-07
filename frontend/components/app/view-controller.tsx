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

export function ViewController({
  appConfig,
  learningMode,
  onLearningModeChange,
}: ViewControllerProps) {
  const session = useSessionContext();
  const agent = useAgent();
  const shouldReduceMotion = useReducedMotion();
  const [isStarting, setIsStarting] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const handlingFailure = useRef(false);

  useEffect(() => {
    if (agent.state !== 'failed' || !session.isConnected) {
      handlingFailure.current = false;
      return;
    }

    if (handlingFailure.current) return;
    handlingFailure.current = true;
    setConnectionError(true);
    void session.end().catch(() => undefined);
  }, [agent.state, session]);

  const handleStart = async () => {
    if (isStarting) return;

    setConnectionError(false);
    setIsStarting(true);
    try {
      await session.start();
    } catch {
      setConnectionError(true);
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
          <WelcomeView
            learningMode={learningMode}
            onLearningModeChange={onLearningModeChange}
            onStartCall={handleStart}
            isConnecting={isStarting}
            connectionError={connectionError}
          />
        </motion.div>
      )}
      {session.isConnected && (
        <motion.div key="session-view" {...motionProps}>
          <FinEdSessionView appConfig={appConfig} learningMode={learningMode} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
