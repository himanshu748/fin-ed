'use client';

import {
  type PropsWithChildren,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useAgent, useSessionContext } from '@livekit/components-react';
import {
  HUMAN_HELP_RPC_METHOD,
  type HumanHelpRequest,
  createHumanHelpRpcHandler,
} from '@/lib/human-help';

interface HumanHelpContextValue {
  requests: HumanHelpRequest[];
  activeRequest: HumanHelpRequest | null;
  isOpen: boolean;
  listRequests(): HumanHelpRequest[];
  viewRequest(referenceId: string): void;
  open(): void;
  close(): void;
}

const HumanHelpContext = createContext<HumanHelpContextValue | null>(null);

export function registerHumanHelpRpcHandler(
  localParticipant: {
    registerRpcMethod(method: string, handler: ReturnType<typeof createHumanHelpRpcHandler>): void;
    unregisterRpcMethod(method: string): void;
  },
  expectedAgentIdentity: string,
  showRequest: (request: HumanHelpRequest) => void
) {
  const handler = createHumanHelpRpcHandler(expectedAgentIdentity, showRequest);
  localParticipant.registerRpcMethod(HUMAN_HELP_RPC_METHOD, handler);
  return () => localParticipant.unregisterRpcMethod(HUMAN_HELP_RPC_METHOD);
}

export function HumanHelpProvider({ children }: PropsWithChildren) {
  const agent = useAgent();
  const session = useSessionContext();
  const [requests, setRequests] = useState<HumanHelpRequest[]>([]);
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const agentParticipant = agent.isConnected ? agent.internal.agentParticipant : null;
  const expectedAgentIdentity = agentParticipant?.identity?.trim() || null;

  const showRequest = useCallback((request: HumanHelpRequest) => {
    setRequests((current) => [
      request,
      ...current.filter((item) => item.reference_id !== request.reference_id),
    ]);
    setActiveReferenceId(request.reference_id);
    setIsOpen(true);
  }, []);

  useEffect(() => {
    if (!expectedAgentIdentity) return;
    try {
      return registerHumanHelpRpcHandler(
        session.room.localParticipant,
        expectedAgentIdentity,
        showRequest
      );
    } catch {
      return;
    }
  }, [expectedAgentIdentity, session.room.localParticipant, showRequest]);

  const value = useMemo<HumanHelpContextValue>(
    () => ({
      requests,
      activeRequest:
        requests.find((request) => request.reference_id === activeReferenceId) ??
        requests[0] ??
        null,
      isOpen,
      listRequests: () => [...requests],
      viewRequest: (referenceId) => {
        if (requests.some((request) => request.reference_id === referenceId)) {
          setActiveReferenceId(referenceId);
          setIsOpen(true);
        }
      },
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
    }),
    [activeReferenceId, isOpen, requests]
  );

  return <HumanHelpContext.Provider value={value}>{children}</HumanHelpContext.Provider>;
}

export function useHumanHelp(): HumanHelpContextValue {
  const context = useContext(HumanHelpContext);
  if (!context) throw new Error('useHumanHelp must be used inside HumanHelpProvider');
  return context;
}
