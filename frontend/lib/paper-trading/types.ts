export const PAPER_PORTFOLIO_SCHEMA_VERSION = 1 as const;
export const PAPER_STARTING_CASH_PAISE = 10_000_000 as const;

export type PaperSide = 'buy' | 'sell';
export type PaperChargeStatus = 'estimated' | 'unavailable';

export interface PaperOrderDraft {
  draftId: string;
  side: PaperSide;
  exchange: string;
  symbolToken: string;
  tradingSymbol: string;
  quantity: number;
  pricePaise: number;
  quoteProvider: string;
  quoteTime: string;
  expiresAt: string;
  notionalPaise: number;
  chargePaise: number | null;
  cashEffectPaise: number | null;
  chargeStatus: PaperChargeStatus;
}

export interface PaperHolding {
  exchange: string;
  symbolToken: string;
  tradingSymbol: string;
  quantity: number;
  costBasisPaise: number;
  averageCostPaise: number;
}

export interface PaperFill {
  draftId: string;
  side: PaperSide;
  exchange: string;
  symbolToken: string;
  tradingSymbol: string;
  quantity: number;
  fillPricePaise: number;
  notionalPaise: number;
  chargesPaise: number;
  cashEffectPaise: number;
  realizedPnlPaise: number;
  filledAt: string;
}

export interface PaperPortfolio {
  schemaVersion: 1;
  portfolioId: string;
  revision: number;
  startingCashPaise: 10_000_000;
  cashPaise: number;
  holdings: PaperHolding[];
  fills: PaperFill[];
  appliedDraftIds: string[];
  createdAt: string;
  updatedAt: string;
}

export type PaperAction =
  | { type: 'confirmDraft'; draft: PaperOrderDraft; now: string }
  | { type: 'reset'; now: string };

export type LoadResult =
  | { status: 'missing' }
  | { status: 'ready'; portfolio: PaperPortfolio }
  | { status: 'corrupt'; raw: string | null }
  | { status: 'unavailable' };

export type SaveResult =
  | { status: 'saved'; portfolio: PaperPortfolio }
  | { status: 'stale'; portfolio: PaperPortfolio }
  | { status: 'aborted'; reason: 'commit-precondition' }
  | { status: 'corrupt'; raw: string | null }
  | { status: 'unavailable' };

export interface SavePaperPortfolioOptions {
  canCommit?(): boolean;
}

export interface PaperPortfolioStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface PaperPortfolioLockCoordinator {
  request<T>(
    name: string,
    options: { mode: 'exclusive' },
    callback: () => T | Promise<T>
  ): Promise<T>;
}
