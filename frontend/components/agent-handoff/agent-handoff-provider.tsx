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
  AGENT_STATUS_RPC_METHOD,
  type ActiveAgentStatus,
  FINED_ACTIVE_AGENT_STATUS,
  createAgentStatusRpcHandler,
} from '@/lib/agent-handoff';

interface AgentHandoffContextValue {
  activeAgent: ActiveAgentStatus;
}

interface AgentStatusRpcRegistry {
  registerRpcMethod(method: string, handler: ReturnType<typeof createAgentStatusRpcHandler>): void;
  unregisterRpcMethod(method: string): void;
}

const AgentHandoffContext = createContext<AgentHandoffContextValue>({
  activeAgent: FINED_ACTIVE_AGENT_STATUS,
});

export function registerAgentStatusRpcHandler(
  localParticipant: AgentStatusRpcRegistry,
  expectedAgentIdentity: string,
  applyStatus: (status: ActiveAgentStatus) => void
) {
  const handler = createAgentStatusRpcHandler(expectedAgentIdentity, applyStatus);
  localParticipant.registerRpcMethod(AGENT_STATUS_RPC_METHOD, handler);
  return () => localParticipant.unregisterRpcMethod(AGENT_STATUS_RPC_METHOD);
}

export function AgentHandoffProvider({ children }: PropsWithChildren) {
  const agent = useAgent();
  const session = useSessionContext();
  const [activeAgent, setActiveAgent] = useState<ActiveAgentStatus>(FINED_ACTIVE_AGENT_STATUS);
  const agentParticipant = agent.isConnected ? agent.internal.agentParticipant : null;
  const expectedAgentIdentity = agentParticipant?.identity.trim() || null;
  const agentParticipantSid = agentParticipant?.sid.trim() || null;
  const applyStatus = useCallback((status: ActiveAgentStatus) => setActiveAgent(status), []);

  useEffect(() => {
    setActiveAgent(FINED_ACTIVE_AGENT_STATUS);
  }, [agentParticipant, agentParticipantSid, expectedAgentIdentity]);

  useEffect(() => {
    if (!expectedAgentIdentity) return;
    try {
      return registerAgentStatusRpcHandler(
        session.room.localParticipant,
        expectedAgentIdentity,
        applyStatus
      );
    } catch {
      return;
    }
  }, [
    agentParticipant,
    agentParticipantSid,
    applyStatus,
    expectedAgentIdentity,
    session.room.localParticipant,
  ]);

  const value = useMemo<AgentHandoffContextValue>(() => ({ activeAgent }), [activeAgent]);

  return <AgentHandoffContext.Provider value={value}>{children}</AgentHandoffContext.Provider>;
}

export function useAgentHandoff(): AgentHandoffContextValue {
  return useContext(AgentHandoffContext);
}
