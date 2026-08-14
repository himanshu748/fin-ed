'use client';

import { useMemo, useState } from 'react';
import { useSession } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentHandoffProvider } from '@/components/agent-handoff/agent-handoff-provider';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ViewController } from '@/components/app/view-controller';
import { HumanHelpProvider } from '@/components/human-help/escalation-provider';
import { PaperTradingProvider } from '@/components/paper-trading/paper-trading-provider';
import { useDebugMode } from '@/hooks/useDebug';
import { type LearningMode, participantMetadataForLearningMode } from '@/lib/learning-modes';
import { getPersistentSessionRoom } from '@/lib/session-room';
import { createModeScopedTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const [learningMode, setLearningMode] = useState<LearningMode>('general');
  const room = useMemo(getPersistentSessionRoom, []);
  const participantMetadata = useMemo(
    () => participantMetadataForLearningMode(learningMode),
    [learningMode]
  );

  const tokenSource = useMemo(
    () => createModeScopedTokenSource(appConfig, participantMetadata),
    [appConfig, participantMetadata]
  );

  const fetchOptions = useMemo(
    () => ({
      ...(appConfig.agentName ? { agentName: appConfig.agentName } : {}),
      participantMetadata,
      room,
    }),
    [appConfig.agentName, participantMetadata, room]
  );

  const session = useSession(tokenSource, fetchOptions);

  return (
    <AgentSessionProvider session={session}>
      <AgentHandoffProvider>
        <HumanHelpProvider>
          <PaperTradingProvider>
            <AppSetup />
            <main className="min-h-svh">
              <ViewController
                appConfig={appConfig}
                learningMode={learningMode}
                onLearningModeChange={setLearningMode}
              />
            </main>
            <StartAudioButton
              label="Allow audio"
              className="fixed right-4 bottom-4 z-[70] border border-[var(--ledger-rule)]"
            />
          </PaperTradingProvider>
        </HumanHelpProvider>
      </AgentHandoffProvider>
    </AgentSessionProvider>
  );
}
