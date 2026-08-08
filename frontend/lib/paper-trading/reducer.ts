import { assertPaperOrderDraft, decodePaperPortfolio } from './schema';
import {
  PAPER_PORTFOLIO_SCHEMA_VERSION,
  PAPER_STARTING_CASH_PAISE,
  type PaperAction,
  type PaperFill,
  type PaperHolding,
  type PaperPortfolio,
} from './types';

function assertTimestamp(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new Error('Invalid paper portfolio timestamp');
  }
  return value;
}

function safeInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value)) throw new Error(`${field} must be a safe integer`);
  return value;
}

function averageCost(costBasisPaise: number, quantity: number): number {
  const roundedNumerator = safeInteger(
    costBasisPaise + Math.floor(quantity / 2),
    'average cost paise'
  );
  return safeInteger(Math.floor(roundedNumerator / quantity), 'average cost paise');
}

function holdingIndex(
  holdings: readonly PaperHolding[],
  exchange: string,
  symbolToken: string
): number {
  return holdings.findIndex(
    (holding) => holding.exchange === exchange && holding.symbolToken === symbolToken
  );
}

function portfolioId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return `paper-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createPaperPortfolio(now: string, id = portfolioId()): PaperPortfolio {
  const timestamp = assertTimestamp(now);
  if (typeof id !== 'string' || !id.trim()) throw new Error('Paper portfolio id must be non-empty');
  return {
    schemaVersion: PAPER_PORTFOLIO_SCHEMA_VERSION,
    portfolioId: id,
    revision: 0,
    startingCashPaise: PAPER_STARTING_CASH_PAISE,
    cashPaise: PAPER_STARTING_CASH_PAISE,
    holdings: [],
    fills: [],
    appliedDraftIds: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

function confirmDraft(
  state: PaperPortfolio,
  action: Extract<PaperAction, { type: 'confirmDraft' }>
): PaperPortfolio {
  const now = assertTimestamp(action.now);
  let draft;
  try {
    draft = assertPaperOrderDraft(action.draft);
  } catch {
    throw new Error('Unknown paper draft');
  }
  if (draft.exchange !== 'NSE') throw new Error('Paper fills are limited to NSE');
  if (Date.parse(draft.expiresAt) <= Date.parse(now)) throw new Error('Paper draft has expired');
  if (state.appliedDraftIds.includes(draft.draftId))
    throw new Error('Paper draft was already applied');
  if (
    draft.chargeStatus !== 'estimated' ||
    draft.chargePaise === null ||
    draft.cashEffectPaise === null
  ) {
    throw new Error('Paper draft charges are unavailable');
  }

  const index = holdingIndex(state.holdings, draft.exchange, draft.symbolToken);
  const currentHolding = index < 0 ? undefined : state.holdings[index];
  let cashPaise: number;
  let holdings: PaperHolding[];
  let realizedPnlPaise = 0;

  if (draft.side === 'buy') {
    if (state.cashPaise < -draft.cashEffectPaise)
      throw new Error('Insufficient cash for paper buy');
    cashPaise = safeInteger(state.cashPaise + draft.cashEffectPaise, 'cash paise');
    const quantity = safeInteger(
      (currentHolding?.quantity ?? 0) + draft.quantity,
      'holding quantity'
    );
    const costBasisPaise = safeInteger(
      (currentHolding?.costBasisPaise ?? 0) + draft.notionalPaise + draft.chargePaise,
      'cost basis paise'
    );
    const nextHolding: PaperHolding = {
      exchange: draft.exchange,
      symbolToken: draft.symbolToken,
      tradingSymbol: draft.tradingSymbol,
      quantity,
      costBasisPaise,
      averageCostPaise: averageCost(costBasisPaise, quantity),
    };
    holdings = currentHolding
      ? state.holdings.map((holding, holdingPosition) =>
          holdingPosition === index ? nextHolding : { ...holding }
        )
      : [...state.holdings.map((holding) => ({ ...holding })), nextHolding];
  } else {
    if (!currentHolding || currentHolding.quantity < draft.quantity) {
      throw new Error('Insufficient holdings for paper sell');
    }
    cashPaise = safeInteger(state.cashPaise + draft.cashEffectPaise, 'cash paise');
    const soldCostNumerator = safeInteger(
      currentHolding.costBasisPaise * draft.quantity,
      'sold cost basis paise'
    );
    const costSoldPaise = safeInteger(
      Math.floor(soldCostNumerator / currentHolding.quantity),
      'sold cost basis paise'
    );
    realizedPnlPaise = safeInteger(draft.cashEffectPaise - costSoldPaise, 'realized P&L paise');
    const quantity = currentHolding.quantity - draft.quantity;
    if (quantity === 0) {
      holdings = state.holdings
        .filter((_, holdingPosition) => holdingPosition !== index)
        .map((holding) => ({ ...holding }));
    } else {
      const costBasisPaise = safeInteger(
        currentHolding.costBasisPaise - costSoldPaise,
        'cost basis paise'
      );
      const nextHolding: PaperHolding = {
        ...currentHolding,
        quantity,
        costBasisPaise,
        averageCostPaise: averageCost(costBasisPaise, quantity),
      };
      holdings = state.holdings.map((holding, holdingPosition) =>
        holdingPosition === index ? nextHolding : { ...holding }
      );
    }
  }

  const fill: PaperFill = {
    draftId: draft.draftId,
    side: draft.side,
    exchange: draft.exchange,
    symbolToken: draft.symbolToken,
    tradingSymbol: draft.tradingSymbol,
    quantity: draft.quantity,
    fillPricePaise: draft.pricePaise,
    notionalPaise: draft.notionalPaise,
    chargesPaise: draft.chargePaise,
    cashEffectPaise: draft.cashEffectPaise,
    realizedPnlPaise,
    filledAt: now,
  };
  return {
    ...state,
    revision: safeInteger(state.revision + 1, 'revision'),
    cashPaise,
    holdings,
    fills: [...state.fills.map((existing) => ({ ...existing })), fill],
    appliedDraftIds: [...state.appliedDraftIds, draft.draftId],
    updatedAt: now,
  };
}

export function reducePaperPortfolio(state: PaperPortfolio, action: PaperAction): PaperPortfolio {
  const current = decodePaperPortfolio(state);
  if (!action || typeof action !== 'object') throw new Error('Unknown paper portfolio action');
  if (action.type === 'confirmDraft') return confirmDraft(current, action);
  if (action.type === 'reset') {
    const now = assertTimestamp(action.now);
    return {
      ...createPaperPortfolio(now, current.portfolioId),
      revision: safeInteger(current.revision + 1, 'revision'),
      createdAt: current.createdAt,
    };
  }
  throw new Error('Unknown paper portfolio action');
}
