'use client';

import {
  type PropsWithChildren,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { RpcInvocationData } from 'livekit-client';
import { useAgent, useSessionContext } from '@livekit/components-react';
import { createPaperPortfolio, reducePaperPortfolio } from '@/lib/paper-trading/reducer';
import { decodePaperOrderDraft } from '@/lib/paper-trading/schema';
import { loadPaperPortfolio, savePaperPortfolio } from '@/lib/paper-trading/storage';
import type {
  PaperOrderDraft,
  PaperPortfolio,
  PaperPortfolioLockCoordinator,
  PaperPortfolioStorage,
  SaveResult,
} from '@/lib/paper-trading/types';

const MAX_RPC_PAYLOAD_BYTES = 15_000;
const ORDER_RESULT_METHOD = 'fined.paper.v1.order_result';
const ORDER_RESULT_TIMEOUT_MS = 10_000;
const PERSISTENCE_ERROR = 'Paper portfolio persistence is unavailable.';
const STALE_ERROR = 'The paper portfolio changed in another tab. The latest portfolio was loaded.';

const RPC_METHODS = {
  openDashboard: 'fined.paper.v1.open_dashboard',
  prepareOrder: 'fined.paper.v1.prepare_order',
  getPortfolioSummary: 'fined.paper.v1.get_portfolio_summary',
} as const;

type PaperInvocation = Pick<RpcInvocationData, 'callerIdentity' | 'payload'>;
type PaperRpcHandler = (data: PaperInvocation) => Promise<string>;

export interface PaperRpcHandlers {
  openDashboard: PaperRpcHandler;
  prepareOrder: PaperRpcHandler;
  getPortfolioSummary: PaperRpcHandler;
}

export interface PaperRpcDependencies {
  expectedAgentIdentity: string;
  getPortfolio(): PaperPortfolio;
  getDraft(): PaperOrderDraft | null;
  now(): string;
  openDashboard(): void;
  prepareDraft(draft: PaperOrderDraft): void;
}

interface PaperRoomRpcRegistry {
  registerRpcMethod(method: string, handler: PaperRpcHandler): void;
  unregisterRpcMethod(method: string): void;
}

interface PaperOrderResultPayload {
  version: 1;
  paper: true;
  draft_id: string;
  side: 'buy' | 'sell';
  trading_symbol: string;
  quantity: number;
  fill_price_paise: number;
  simulated_at: string;
  cash_paise: number;
}

interface PaperRpcSender {
  performRpc(options: {
    destinationIdentity: string;
    method: string;
    payload: string;
    responseTimeout: number;
  }): Promise<string>;
}

export interface ConfirmPaperDraftDependencies {
  portfolio: PaperPortfolio;
  draft: PaperOrderDraft;
  now: string;
  storage: PaperPortfolioStorage | null | undefined;
  coordinator?: PaperPortfolioLockCoordinator | null;
  sendOrderResult(payload: PaperOrderResultPayload): Promise<string>;
}

export type PaperTradingView = 'session' | 'dashboard';

export interface PaperTradingContextValue {
  view: PaperTradingView;
  portfolio: PaperPortfolio;
  draft: PaperOrderDraft | null;
  error: string | null;
  openDashboard(): void;
  closeDashboard(): void;
  confirmDraft(): Promise<boolean>;
  resetPortfolio(): Promise<boolean>;
}

interface AgentIdentitySource {
  isConnected: boolean;
  internal: { agentParticipant: { identity: string } | null };
}

export function connectedAgentIdentity(agent: AgentIdentitySource): string | null {
  const identity = agent.isConnected ? agent.internal.agentParticipant?.identity : null;
  return typeof identity === 'string' && identity.trim() ? identity : null;
}

export function sendPaperOrderResult(
  localParticipant: PaperRpcSender,
  expectedAgentIdentity: string,
  payload: PaperOrderResultPayload
): Promise<string> {
  if (typeof expectedAgentIdentity !== 'string' || !expectedAgentIdentity.trim()) {
    return Promise.reject(new Error('Expected paper RPC agent identity must be non-empty'));
  }
  return localParticipant.performRpc({
    destinationIdentity: expectedAgentIdentity,
    method: ORDER_RESULT_METHOD,
    payload: JSON.stringify(payload),
    responseTimeout: ORDER_RESULT_TIMEOUT_MS,
  });
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function requireIntegerNumberTokens(payload: string): void {
  let index = 0;
  let inString = false;
  let escaped = false;
  while (index < payload.length) {
    const character = payload[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === '"') inString = false;
      index += 1;
      continue;
    }
    if (character === '"') {
      inString = true;
      index += 1;
      continue;
    }
    if (character === '-' || (character >= '0' && character <= '9')) {
      const token = payload.slice(index).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
      if (!token || !/^-?(?:0|[1-9]\d*)$/.test(token[0])) {
        throw new Error('Paper RPC numeric values must be whole numbers');
      }
      index += token[0].length;
      continue;
    }
    index += 1;
  }
}

function decodeObject(payload: string): Record<string, unknown> {
  if (typeof payload !== 'string' || utf8ByteLength(payload) > MAX_RPC_PAYLOAD_BYTES) {
    throw new Error('Paper RPC payload exceeds the maximum size');
  }
  requireIntegerNumberTokens(payload);
  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    throw new Error('Paper RPC payload must be valid JSON');
  }
  if (typeof decoded !== 'object' || decoded === null || Array.isArray(decoded)) {
    throw new Error('Paper RPC payload must be an object');
  }
  return decoded as Record<string, unknown>;
}

function requireExactKeys(value: Record<string, unknown>, expected: readonly string[]): void {
  const keys = Object.keys(value);
  if (keys.length !== expected.length || keys.some((key) => !expected.includes(key))) {
    throw new Error('Paper RPC payload has an invalid shape');
  }
}

function decodeEmptyPaperRequest(payload: string): void {
  const decoded = decodeObject(payload);
  requireExactKeys(decoded, ['version', 'paper']);
  if (decoded.version !== 1 || decoded.paper !== true) {
    throw new Error('Paper RPC payload has an unsupported version');
  }
}

function authorize(callerIdentity: string, expectedAgentIdentity: string): void {
  if (callerIdentity !== expectedAgentIdentity) {
    throw new Error('Paper RPC caller is not authorized');
  }
}

export function createPaperRpcHandlers(dependencies: PaperRpcDependencies): PaperRpcHandlers {
  if (
    typeof dependencies.expectedAgentIdentity !== 'string' ||
    !dependencies.expectedAgentIdentity.trim()
  ) {
    throw new Error('Expected paper RPC agent identity must be non-empty');
  }

  const openDashboard: PaperRpcHandler = async ({ callerIdentity, payload }) => {
    authorize(callerIdentity, dependencies.expectedAgentIdentity);
    decodeEmptyPaperRequest(payload);
    dependencies.openDashboard();
    return JSON.stringify({ version: 1, paper: true, opened: true });
  };

  const prepareOrder: PaperRpcHandler = async ({ callerIdentity, payload }) => {
    authorize(callerIdentity, dependencies.expectedAgentIdentity);
    const decoded = decodeObject(payload);
    const draft = decodePaperOrderDraft(decoded);
    const portfolio = dependencies.getPortfolio();
    if (portfolio.appliedDraftIds.includes(draft.draftId)) {
      throw new Error('Paper draft was already applied');
    }
    if (dependencies.getDraft()?.draftId === draft.draftId) {
      throw new Error('Paper draft was already prepared');
    }
    if (Date.parse(draft.expiresAt) <= Date.parse(dependencies.now())) {
      throw new Error('Paper draft has expired');
    }
    dependencies.prepareDraft(draft);
    dependencies.openDashboard();
    return JSON.stringify({
      version: 1,
      paper: true,
      prepared: true,
      draft_id: draft.draftId,
    });
  };

  const getPortfolioSummary: PaperRpcHandler = async ({ callerIdentity, payload }) => {
    authorize(callerIdentity, dependencies.expectedAgentIdentity);
    decodeEmptyPaperRequest(payload);
    const portfolio = dependencies.getPortfolio();
    const holdingsValuePaise = portfolio.holdings.reduce((total, holding) => {
      const next = total + holding.costBasisPaise;
      if (!Number.isSafeInteger(next)) throw new Error('Paper portfolio summary is unavailable');
      return next;
    }, 0);
    const totalValuePaise = portfolio.cashPaise + holdingsValuePaise;
    if (!Number.isSafeInteger(totalValuePaise) || totalValuePaise < 0) {
      throw new Error('Paper portfolio summary is unavailable');
    }
    return JSON.stringify({
      version: 1,
      paper: true,
      cash_paise: portfolio.cashPaise,
      holdings_value_paise: holdingsValuePaise,
      total_value_paise: totalValuePaise,
    });
  };

  return { openDashboard, prepareOrder, getPortfolioSummary };
}

export function registerPaperRpcHandlers(
  room: PaperRoomRpcRegistry,
  handlers: PaperRpcHandlers
): () => void {
  const registrations = [
    [RPC_METHODS.openDashboard, handlers.openDashboard],
    [RPC_METHODS.prepareOrder, handlers.prepareOrder],
    [RPC_METHODS.getPortfolioSummary, handlers.getPortfolioSummary],
  ] as const;
  const installed: string[] = [];
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    for (const method of installed.reverse()) {
      try {
        room.unregisterRpcMethod(method);
      } catch {
        // Continue removing the remaining methods during teardown.
      }
    }
  };
  try {
    for (const [method, handler] of registrations) {
      room.registerRpcMethod(method, handler);
      installed.push(method);
    }
  } catch (error) {
    cleanup();
    throw error;
  }
  return cleanup;
}

export async function confirmPaperDraft(
  dependencies: ConfirmPaperDraftDependencies
): Promise<SaveResult> {
  const candidate = reducePaperPortfolio(dependencies.portfolio, {
    type: 'confirmDraft',
    draft: dependencies.draft,
    now: dependencies.now,
  });
  const result = await savePaperPortfolio(
    dependencies.storage,
    candidate,
    dependencies.coordinator
  );
  if (result.status !== 'saved') return result;

  const fill = result.portfolio.fills[result.portfolio.fills.length - 1];
  const payload: PaperOrderResultPayload = {
    version: 1,
    paper: true,
    draft_id: fill.draftId,
    side: fill.side,
    trading_symbol: fill.tradingSymbol,
    quantity: fill.quantity,
    fill_price_paise: fill.fillPricePaise,
    simulated_at: fill.filledAt,
    cash_paise: result.portfolio.cashPaise,
  };
  try {
    void Promise.resolve(dependencies.sendOrderResult(payload)).catch(() => undefined);
  } catch {
    // The persisted browser result remains successful even when voice acknowledgement fails.
  }
  return result;
}

function browserStorage(): PaperPortfolioStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

const PaperTradingContext = createContext<PaperTradingContextValue | null>(null);

export function usePaperTrading(): PaperTradingContextValue {
  const context = useContext(PaperTradingContext);
  if (!context) throw new Error('usePaperTrading must be used inside PaperTradingProvider');
  return context;
}

export function PaperTradingProvider({ children }: PropsWithChildren) {
  const session = useSessionContext();
  const agent = useAgent();
  const [view, setView] = useState<PaperTradingView>('session');
  const [portfolio, setPortfolio] = useState(() => createPaperPortfolio(new Date().toISOString()));
  const [draft, setDraft] = useState<PaperOrderDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const portfolioRef = useRef(portfolio);
  const draftRef = useRef(draft);

  const updatePortfolio = useCallback((next: PaperPortfolio) => {
    portfolioRef.current = next;
    setPortfolio(next);
  }, []);
  const updateDraft = useCallback((next: PaperOrderDraft | null) => {
    draftRef.current = next;
    setDraft(next);
  }, []);
  const openDashboard = useCallback(() => setView('dashboard'), []);
  const closeDashboard = useCallback(() => setView('session'), []);

  useEffect(() => {
    const loaded = loadPaperPortfolio(browserStorage());
    if (loaded.status === 'ready') updatePortfolio(loaded.portfolio);
    else if (loaded.status === 'corrupt' || loaded.status === 'unavailable') {
      setError(PERSISTENCE_ERROR);
    }
  }, [updatePortfolio]);

  const expectedAgentIdentity = connectedAgentIdentity(agent);
  const handlers = useMemo(
    () =>
      expectedAgentIdentity
        ? createPaperRpcHandlers({
            expectedAgentIdentity,
            getPortfolio: () => portfolioRef.current,
            getDraft: () => draftRef.current,
            now: () => new Date().toISOString(),
            openDashboard,
            prepareDraft: (next) => {
              updateDraft(next);
              setError(null);
            },
          })
        : null,
    [expectedAgentIdentity, openDashboard, updateDraft]
  );

  useEffect(() => {
    if (!handlers) return;
    return registerPaperRpcHandlers(session.room, handlers);
  }, [handlers, session.room]);

  const confirmDraft = useCallback(async () => {
    const currentDraft = draftRef.current;
    if (!currentDraft || !expectedAgentIdentity) {
      setError('No active paper draft is available to confirm.');
      return false;
    }
    try {
      const result = await confirmPaperDraft({
        portfolio: portfolioRef.current,
        draft: currentDraft,
        now: new Date().toISOString(),
        storage: browserStorage(),
        sendOrderResult: (payload) =>
          sendPaperOrderResult(session.room.localParticipant, expectedAgentIdentity, payload),
      });
      if (result.status === 'saved') {
        updatePortfolio(result.portfolio);
        updateDraft(null);
        setError(null);
        return true;
      }
      if (result.status === 'stale') {
        updatePortfolio(result.portfolio);
        if (result.portfolio.appliedDraftIds.includes(currentDraft.draftId)) updateDraft(null);
        setError(STALE_ERROR);
        return false;
      }
      setError(PERSISTENCE_ERROR);
      return false;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The paper order could not be confirmed.');
      return false;
    }
  }, [expectedAgentIdentity, session.room.localParticipant, updateDraft, updatePortfolio]);

  const resetPortfolio = useCallback(async () => {
    try {
      const candidate = reducePaperPortfolio(portfolioRef.current, {
        type: 'reset',
        now: new Date().toISOString(),
      });
      const result = await savePaperPortfolio(browserStorage(), candidate);
      if (result.status === 'saved') {
        updatePortfolio(result.portfolio);
        updateDraft(null);
        setError(null);
        return true;
      }
      if (result.status === 'stale') {
        updatePortfolio(result.portfolio);
        setError(STALE_ERROR);
        return false;
      }
      setError(PERSISTENCE_ERROR);
      return false;
    } catch {
      setError(PERSISTENCE_ERROR);
      return false;
    }
  }, [updateDraft, updatePortfolio]);

  const value = useMemo<PaperTradingContextValue>(
    () => ({
      view,
      portfolio,
      draft,
      error,
      openDashboard,
      closeDashboard,
      confirmDraft,
      resetPortfolio,
    }),
    [closeDashboard, confirmDraft, draft, error, openDashboard, portfolio, resetPortfolio, view]
  );

  return <PaperTradingContext.Provider value={value}>{children}</PaperTradingContext.Provider>;
}
