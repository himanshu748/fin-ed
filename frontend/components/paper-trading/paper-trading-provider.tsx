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
import {
  type PaperHoldingQuotes,
  paperHoldingKey,
  requestPaperHoldingQuotes,
} from '@/lib/paper-trading/valuation';

const MAX_RPC_PAYLOAD_BYTES = 15_000;
const ORDER_RESULT_METHOD = 'fined.paper.v1.order_result';
const ORDER_RESULT_TIMEOUT_MS = 10_000;
const PERSISTENCE_ERROR = 'Paper portfolio persistence is unavailable.';
const STALE_ERROR = 'The paper portfolio changed in another tab. The latest portfolio was loaded.';
const SESSION_ERROR = 'Paper draft belongs to a different agent session.';

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
  expectedAgentSessionKey: string;
  getPortfolio(): PaperPortfolio;
  getDraft(): PreparedPaperDraft | null;
  getReadiness(): PaperLedgerReadiness;
  now(): string;
  openDashboard(): void;
  prepareDraft(draft: PreparedPaperDraft): void;
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
  preparedAgentIdentity: string;
  currentAgentIdentity: string;
  preparedAgentSessionKey: string;
  getCurrentAgentSessionKey(): string | null;
  now: string;
  storage: PaperPortfolioStorage | null | undefined;
  coordinator?: PaperPortfolioLockCoordinator | null;
  sendOrderResult(payload: PaperOrderResultPayload): Promise<string>;
}

export type PaperTradingView = 'session' | 'dashboard';
export type PaperLedgerReadiness = 'initializing' | 'ready' | 'unavailable' | 'corrupt';
export type PaperQuoteStatus = 'idle' | 'loading' | 'ready' | 'partial' | 'unavailable';

export interface PreparedPaperDraft {
  draft: PaperOrderDraft;
  agentIdentity: string;
  agentSessionKey: string;
}

export interface PaperLedgerInitialization {
  readiness: PaperLedgerReadiness;
  portfolio: PaperPortfolio;
}

export interface PaperLedgerState extends PaperLedgerInitialization {
  draft: PreparedPaperDraft | null;
  error: string | null;
}

export interface PaperTradingContextValue {
  view: PaperTradingView;
  readiness: PaperLedgerReadiness;
  portfolio: PaperPortfolio;
  draft: PaperOrderDraft | null;
  holdingQuotes: PaperHoldingQuotes;
  quoteStatus: PaperQuoteStatus;
  error: string | null;
  openDashboard(): void;
  closeDashboard(): void;
  confirmDraft(): Promise<boolean>;
  resetPortfolio(): Promise<boolean>;
  refreshHoldingQuotes(): Promise<boolean>;
}

interface AgentIdentitySource {
  isConnected: boolean;
  internal: { agentParticipant: { identity: string; sid?: string } | null };
}

interface ConnectedAgentSession {
  identity: string;
  sessionKey: string;
}

const participantGenerations = new WeakMap<object, string>();
let participantGenerationSequence = 0;

export function connectedAgentIdentity(agent: AgentIdentitySource): string | null {
  const identity = agent.isConnected ? agent.internal.agentParticipant?.identity : null;
  return typeof identity === 'string' && identity.trim() ? identity : null;
}

export function connectedAgentSession(agent: AgentIdentitySource): ConnectedAgentSession | null {
  const identity = connectedAgentIdentity(agent);
  const participant = agent.internal.agentParticipant;
  if (!identity || !participant) return null;
  const sid = typeof participant.sid === 'string' ? participant.sid.trim() : '';
  if (sid) return { identity, sessionKey: `${identity}:${sid}` };
  let generation = participantGenerations.get(participant);
  if (!generation) {
    participantGenerationSequence += 1;
    generation = `instance-${participantGenerationSequence}`;
    participantGenerations.set(participant, generation);
  }
  return { identity, sessionKey: `${identity}:${generation}` };
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

function pythonCompatibleUtcTimestamp(value: string): string {
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) throw new Error('Invalid paper result timestamp');
  return timestamp.toISOString().replace(/Z$/, '+00:00');
}

function requireReadyLedger(dependencies: PaperRpcDependencies): void {
  if (dependencies.getReadiness() !== 'ready') {
    throw new Error('Paper portfolio ledger is not ready');
  }
}

export function createPaperRpcHandlers(dependencies: PaperRpcDependencies): PaperRpcHandlers {
  if (
    typeof dependencies.expectedAgentIdentity !== 'string' ||
    !dependencies.expectedAgentIdentity.trim()
  ) {
    throw new Error('Expected paper RPC agent identity must be non-empty');
  }
  if (
    typeof dependencies.expectedAgentSessionKey !== 'string' ||
    !dependencies.expectedAgentSessionKey.trim()
  ) {
    throw new Error('Expected paper RPC agent session must be non-empty');
  }

  const openDashboard: PaperRpcHandler = async ({ callerIdentity, payload }) => {
    authorize(callerIdentity, dependencies.expectedAgentIdentity);
    decodeEmptyPaperRequest(payload);
    dependencies.openDashboard();
    return JSON.stringify({ version: 1, paper: true, opened: true });
  };

  const prepareOrder: PaperRpcHandler = async ({ callerIdentity, payload }) => {
    authorize(callerIdentity, dependencies.expectedAgentIdentity);
    requireReadyLedger(dependencies);
    const decoded = decodeObject(payload);
    const draft = decodePaperOrderDraft(decoded);
    const portfolio = dependencies.getPortfolio();
    if (portfolio.appliedDraftIds.includes(draft.draftId)) {
      throw new Error('Paper draft was already applied');
    }
    if (dependencies.getDraft()?.draft.draftId === draft.draftId) {
      throw new Error('Paper draft was already prepared');
    }
    if (Date.parse(draft.expiresAt) <= Date.parse(dependencies.now())) {
      throw new Error('Paper draft has expired');
    }
    dependencies.prepareDraft({
      draft,
      agentIdentity: dependencies.expectedAgentIdentity,
      agentSessionKey: dependencies.expectedAgentSessionKey,
    });
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
    requireReadyLedger(dependencies);
    decodeEmptyPaperRequest(payload);
    const portfolio = dependencies.getPortfolio();
    const holdingsCostBasisPaise = portfolio.holdings.reduce((total, holding) => {
      const next = total + holding.costBasisPaise;
      if (!Number.isSafeInteger(next)) throw new Error('Paper portfolio summary is unavailable');
      return next;
    }, 0);
    const cashPlusCostBasisPaise = portfolio.cashPaise + holdingsCostBasisPaise;
    if (!Number.isSafeInteger(cashPlusCostBasisPaise) || cashPlusCostBasisPaise < 0) {
      throw new Error('Paper portfolio summary is unavailable');
    }
    return JSON.stringify({
      version: 1,
      paper: true,
      cash_paise: portfolio.cashPaise,
      holdings_cost_basis_paise: holdingsCostBasisPaise,
      cash_plus_cost_basis_paise: cashPlusCostBasisPaise,
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
  const currentAgentSessionKey = dependencies.getCurrentAgentSessionKey();
  if (
    !dependencies.preparedAgentIdentity.trim() ||
    dependencies.preparedAgentIdentity !== dependencies.currentAgentIdentity ||
    !dependencies.preparedAgentSessionKey.trim() ||
    dependencies.preparedAgentSessionKey !== currentAgentSessionKey
  ) {
    throw new Error(SESSION_ERROR);
  }
  const candidate = reducePaperPortfolio(dependencies.portfolio, {
    type: 'confirmDraft',
    draft: dependencies.draft,
    now: dependencies.now,
  });
  const result = await savePaperPortfolio(
    dependencies.storage,
    candidate,
    dependencies.coordinator,
    {
      canCommit: () =>
        dependencies.getCurrentAgentSessionKey() === dependencies.preparedAgentSessionKey,
    }
  );
  if (result.status !== 'saved') return result;
  if (dependencies.getCurrentAgentSessionKey() !== dependencies.preparedAgentSessionKey) {
    return result;
  }

  const fill = result.portfolio.fills[result.portfolio.fills.length - 1];
  const payload: PaperOrderResultPayload = {
    version: 1,
    paper: true,
    draft_id: fill.draftId,
    side: fill.side,
    trading_symbol: fill.tradingSymbol,
    quantity: fill.quantity,
    fill_price_paise: fill.fillPricePaise,
    simulated_at: pythonCompatibleUtcTimestamp(fill.filledAt),
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

function browserLockCoordinator(): PaperPortfolioLockCoordinator | null {
  try {
    const locks = typeof navigator === 'undefined' ? null : navigator.locks;
    return locks && typeof locks.request === 'function'
      ? (locks as unknown as PaperPortfolioLockCoordinator)
      : null;
  } catch {
    return null;
  }
}

export async function initializePaperLedger(
  storage: PaperPortfolioStorage | null | undefined,
  coordinator: PaperPortfolioLockCoordinator | null | undefined,
  now: string
): Promise<PaperLedgerInitialization> {
  const fallback = createPaperPortfolio(now);
  const loaded = loadPaperPortfolio(storage);
  if (loaded.status === 'corrupt') return { readiness: 'corrupt', portfolio: fallback };
  if (loaded.status === 'unavailable') return { readiness: 'unavailable', portfolio: fallback };
  const candidate = loaded.status === 'ready' ? loaded.portfolio : fallback;
  if (!coordinator || typeof coordinator.request !== 'function') {
    return { readiness: 'unavailable', portfolio: candidate };
  }
  const saved = await savePaperPortfolio(storage, candidate, coordinator);
  if (saved.status === 'saved' || saved.status === 'stale') {
    return { readiness: 'ready', portfolio: saved.portfolio };
  }
  return {
    readiness: saved.status === 'corrupt' ? 'corrupt' : 'unavailable',
    portfolio: candidate,
  };
}

export function reconcilePaperSave(
  state: PaperLedgerState,
  result: SaveResult,
  operation: 'confirm' | 'reset'
): PaperLedgerState {
  if (result.status === 'aborted') {
    return {
      readiness: 'ready',
      portfolio: state.portfolio,
      draft: null,
      error: SESSION_ERROR,
    };
  }
  if (result.status === 'saved') {
    return {
      readiness: 'ready',
      portfolio: result.portfolio,
      draft: null,
      error: null,
    };
  }
  if (result.status === 'stale') {
    const draftWasApplied =
      operation === 'confirm' &&
      state.draft !== null &&
      result.portfolio.appliedDraftIds.includes(state.draft.draft.draftId);
    return {
      readiness: 'ready',
      portfolio: result.portfolio,
      draft: draftWasApplied ? null : state.draft,
      error: STALE_ERROR,
    };
  }
  return {
    readiness: result.status,
    portfolio: state.portfolio,
    draft: null,
    error: PERSISTENCE_ERROR,
  };
}

export function reconcileAgentSession(
  state: PaperLedgerState,
  expectedAgentSessionKey: string | null
): PaperLedgerState {
  return state.draft && state.draft.agentSessionKey !== expectedAgentSessionKey
    ? { ...state, draft: null }
    : state;
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
  const [ledger, setLedger] = useState<PaperLedgerState>(() => ({
    readiness: 'initializing',
    portfolio: createPaperPortfolio(new Date().toISOString()),
    draft: null,
    error: null,
  }));
  const ledgerRef = useRef(ledger);
  const [holdingQuotes, setHoldingQuotes] = useState<PaperHoldingQuotes>({});
  const [quoteStatus, setQuoteStatus] = useState<PaperQuoteStatus>('idle');
  const quoteRequestGeneration = useRef(0);

  const updateLedger = useCallback(
    (transition: (current: PaperLedgerState) => PaperLedgerState) => {
      const next = transition(ledgerRef.current);
      ledgerRef.current = next;
      setLedger(next);
    },
    []
  );
  const openDashboard = useCallback(() => setView('dashboard'), []);
  const closeDashboard = useCallback(() => setView('session'), []);

  useEffect(() => {
    let active = true;
    void initializePaperLedger(
      browserStorage(),
      browserLockCoordinator(),
      new Date().toISOString()
    ).then((initialized) => {
      if (!active) return;
      updateLedger((current) => ({
        ...current,
        ...initialized,
        draft: initialized.readiness === 'ready' ? current.draft : null,
        error: initialized.readiness === 'ready' ? current.error : PERSISTENCE_ERROR,
      }));
    });
    return () => {
      active = false;
    };
  }, [updateLedger]);

  const agentSession = connectedAgentSession(agent);
  const expectedAgentIdentity = agentSession?.identity ?? null;
  const expectedAgentSessionKey = agentSession?.sessionKey ?? null;
  const expectedAgentSessionKeyRef = useRef(expectedAgentSessionKey);
  expectedAgentSessionKeyRef.current = expectedAgentSessionKey;
  useEffect(() => {
    updateLedger((current) => reconcileAgentSession(current, expectedAgentSessionKey));
    quoteRequestGeneration.current += 1;
    setHoldingQuotes({});
    setQuoteStatus('idle');
  }, [expectedAgentSessionKey, updateLedger]);
  const handlers = useMemo(
    () =>
      expectedAgentIdentity && expectedAgentSessionKey
        ? createPaperRpcHandlers({
            expectedAgentIdentity,
            expectedAgentSessionKey,
            getPortfolio: () => ledgerRef.current.portfolio,
            getDraft: () => ledgerRef.current.draft,
            getReadiness: () => ledgerRef.current.readiness,
            now: () => new Date().toISOString(),
            openDashboard,
            prepareDraft: (next) => {
              updateLedger((current) => ({ ...current, draft: next }));
            },
          })
        : null,
    [expectedAgentIdentity, expectedAgentSessionKey, openDashboard, updateLedger]
  );

  useEffect(() => {
    if (!handlers) return;
    return registerPaperRpcHandlers(session.room, handlers);
  }, [handlers, session.room]);

  const confirmDraft = useCallback(async () => {
    const current = ledgerRef.current;
    const currentDraft = current.draft;
    if (current.readiness !== 'ready') {
      updateLedger((state) => ({ ...state, error: PERSISTENCE_ERROR }));
      return false;
    }
    if (!currentDraft || !expectedAgentIdentity || !expectedAgentSessionKey) {
      updateLedger((state) => ({
        ...state,
        error: 'No active paper draft is available to confirm.',
      }));
      return false;
    }
    try {
      const result = await confirmPaperDraft({
        portfolio: current.portfolio,
        draft: currentDraft.draft,
        preparedAgentIdentity: currentDraft.agentIdentity,
        currentAgentIdentity: expectedAgentIdentity,
        preparedAgentSessionKey: currentDraft.agentSessionKey,
        getCurrentAgentSessionKey: () => expectedAgentSessionKeyRef.current,
        now: new Date().toISOString(),
        storage: browserStorage(),
        sendOrderResult: (payload) =>
          sendPaperOrderResult(session.room.localParticipant, expectedAgentIdentity, payload),
      });
      updateLedger((state) => reconcilePaperSave(state, result, 'confirm'));
      if (result.status === 'saved') {
        return true;
      }
      return false;
    } catch (cause) {
      updateLedger((state) => ({
        ...state,
        error: cause instanceof Error ? cause.message : 'The paper order could not be confirmed.',
      }));
      return false;
    }
  }, [expectedAgentIdentity, expectedAgentSessionKey, session.room.localParticipant, updateLedger]);

  const resetPortfolio = useCallback(async () => {
    const current = ledgerRef.current;
    if (current.readiness !== 'ready') {
      updateLedger((state) => ({ ...state, error: PERSISTENCE_ERROR }));
      return false;
    }
    try {
      const candidate = reducePaperPortfolio(current.portfolio, {
        type: 'reset',
        now: new Date().toISOString(),
      });
      const result = await savePaperPortfolio(browserStorage(), candidate);
      updateLedger((state) => reconcilePaperSave(state, result, 'reset'));
      if (result.status === 'saved') {
        return true;
      }
      return false;
    } catch {
      updateLedger((state) => ({
        ...state,
        readiness: 'unavailable',
        draft: null,
        error: PERSISTENCE_ERROR,
      }));
      return false;
    }
  }, [updateLedger]);

  const refreshHoldingQuotes = useCallback(async () => {
    const holdings = ledgerRef.current.portfolio.holdings;
    if (!expectedAgentIdentity || !expectedAgentSessionKey || !holdings.length) {
      setHoldingQuotes({});
      setQuoteStatus('idle');
      return false;
    }
    const generation = ++quoteRequestGeneration.current;
    setQuoteStatus('loading');
    try {
      const quotes = await requestPaperHoldingQuotes(
        session.room.localParticipant,
        expectedAgentIdentity,
        holdings
      );
      if (
        generation !== quoteRequestGeneration.current ||
        expectedAgentSessionKeyRef.current !== expectedAgentSessionKey
      ) {
        return false;
      }
      setHoldingQuotes(quotes);
      const quoteCount = holdings.filter((holding) => quotes[paperHoldingKey(holding)]).length;
      setQuoteStatus(
        quoteCount === holdings.length ? 'ready' : quoteCount > 0 ? 'partial' : 'unavailable'
      );
      return quoteCount === holdings.length;
    } catch {
      if (generation !== quoteRequestGeneration.current) return false;
      setHoldingQuotes({});
      setQuoteStatus('unavailable');
      return false;
    }
  }, [expectedAgentIdentity, expectedAgentSessionKey, session.room.localParticipant]);

  useEffect(() => {
    if (view !== 'dashboard' || ledger.portfolio.holdings.length === 0) return;
    void refreshHoldingQuotes();
    const interval = window.setInterval(() => void refreshHoldingQuotes(), 30_000);
    return () => {
      window.clearInterval(interval);
      quoteRequestGeneration.current += 1;
    };
  }, [ledger.portfolio.revision, refreshHoldingQuotes, view]);

  const value = useMemo<PaperTradingContextValue>(
    () => ({
      view,
      readiness: ledger.readiness,
      portfolio: ledger.portfolio,
      draft: ledger.draft?.draft ?? null,
      holdingQuotes,
      quoteStatus,
      error: ledger.error,
      openDashboard,
      closeDashboard,
      confirmDraft,
      resetPortfolio,
      refreshHoldingQuotes,
    }),
    [
      closeDashboard,
      confirmDraft,
      holdingQuotes,
      ledger,
      openDashboard,
      quoteStatus,
      refreshHoldingQuotes,
      resetPortfolio,
      view,
    ]
  );

  return <PaperTradingContext.Provider value={value}>{children}</PaperTradingContext.Provider>;
}
