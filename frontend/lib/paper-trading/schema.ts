import {
  PAPER_PORTFOLIO_SCHEMA_VERSION,
  PAPER_STARTING_CASH_PAISE,
  type PaperFill,
  type PaperHolding,
  type PaperOrderDraft,
  type PaperPortfolio,
} from './types';

const DRAFT_KEYS = [
  'version',
  'paper',
  'draft_id',
  'side',
  'exchange',
  'symbol_token',
  'trading_symbol',
  'quantity',
  'price_paise',
  'quote_provider',
  'quote_time',
  'expires_at',
  'notional_paise',
  'charge_paise',
  'cash_effect_paise',
  'charge_status',
] as const;
const DRAFT_VALUE_KEYS = [
  'draftId',
  'side',
  'exchange',
  'symbolToken',
  'tradingSymbol',
  'quantity',
  'pricePaise',
  'quoteProvider',
  'quoteTime',
  'expiresAt',
  'notionalPaise',
  'chargePaise',
  'cashEffectPaise',
  'chargeStatus',
] as const;
const PORTFOLIO_KEYS = [
  'schemaVersion',
  'portfolioId',
  'revision',
  'startingCashPaise',
  'cashPaise',
  'holdings',
  'fills',
  'appliedDraftIds',
  'createdAt',
  'updatedAt',
] as const;
const HOLDING_KEYS = [
  'exchange',
  'symbolToken',
  'tradingSymbol',
  'quantity',
  'costBasisPaise',
  'averageCostPaise',
] as const;
const FILL_KEYS = [
  'draftId',
  'side',
  'exchange',
  'symbolToken',
  'tradingSymbol',
  'quantity',
  'fillPricePaise',
  'notionalPaise',
  'chargesPaise',
  'cashEffectPaise',
  'realizedPnlPaise',
  'filledAt',
] as const;

function fail(message: string): never {
  throw new Error(`Invalid paper portfolio data: ${message}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireExactKeys(value: Record<string, unknown>, keys: readonly string[]): void {
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) {
    fail('unknown or missing fields');
  }
}

function requireText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) fail(`${field} must be non-empty text`);
  return value;
}

function requireSafeInteger(value: unknown, field: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    fail(`${field} must be a safe integer`);
  }
  return value as number;
}

function requireTimestamp(value: unknown, field: string): string {
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    fail(`${field} must be an ISO timestamp`);
  }
  return value;
}

function requireSide(value: unknown): 'buy' | 'sell' {
  if (value !== 'buy' && value !== 'sell') fail('side must be buy or sell');
  return value;
}

function requireExchange(value: unknown): string {
  const exchange = requireText(value, 'exchange');
  if (exchange !== 'NSE' && exchange !== 'BSE') fail('exchange must be NSE or BSE');
  return exchange;
}

function requireSymbolToken(value: unknown): string {
  const token = requireText(value, 'symbol token');
  if (!/^\d{1,20}$/.test(token)) fail('symbol token must be 1 to 20 digits');
  return token;
}

function safeProduct(left: number, right: number, field: string): number {
  const product = left * right;
  if (!Number.isSafeInteger(product)) fail(`${field} must be a safe integer`);
  return product;
}

function averageCost(costBasisPaise: number, quantity: number): number {
  const roundedNumerator = costBasisPaise + Math.floor(quantity / 2);
  if (!Number.isSafeInteger(roundedNumerator)) fail('average cost must be a safe integer');
  const average = Math.floor(roundedNumerator / quantity);
  if (!Number.isSafeInteger(average)) fail('average cost must be a safe integer');
  return average;
}

function decodeDraftFields(value: unknown, keys: readonly string[]): PaperOrderDraft {
  if (!isRecord(value)) fail('draft must be an object');
  requireExactKeys(value, keys);
  const draftId = requireText(value.draftId, 'draft id');
  const side = requireSide(value.side);
  const exchange = requireExchange(value.exchange);
  const symbolToken = requireSymbolToken(value.symbolToken);
  const tradingSymbol = requireText(value.tradingSymbol, 'trading symbol');
  const quantity = requireSafeInteger(value.quantity, 'quantity', 1);
  const pricePaise = requireSafeInteger(value.pricePaise, 'price paise', 1);
  const quoteProvider = requireText(value.quoteProvider, 'quote provider');
  const quoteTime = requireTimestamp(value.quoteTime, 'quote time');
  const expiresAt = requireTimestamp(value.expiresAt, 'expiry time');
  if (Date.parse(expiresAt) - Date.parse(quoteTime) !== 30_000)
    fail('draft expiry must be 30 seconds');
  const notionalPaise = requireSafeInteger(value.notionalPaise, 'notional paise');
  if (notionalPaise !== safeProduct(quantity, pricePaise, 'notional paise')) {
    fail('notional paise must equal quantity times price paise');
  }
  if (value.chargeStatus !== 'estimated' && value.chargeStatus !== 'unavailable') {
    fail('charge status must be estimated or unavailable');
  }
  const chargeStatus = value.chargeStatus;
  const chargePaise = value.chargePaise;
  const cashEffectPaise = value.cashEffectPaise;
  if (chargeStatus === 'unavailable') {
    if (chargePaise !== null || cashEffectPaise !== null) fail('unavailable charges must be null');
    return {
      draftId,
      side,
      exchange,
      symbolToken,
      tradingSymbol,
      quantity,
      pricePaise,
      quoteProvider,
      quoteTime,
      expiresAt,
      notionalPaise,
      chargePaise: null,
      cashEffectPaise: null,
      chargeStatus,
    };
  }
  const parsedCharge = requireSafeInteger(chargePaise, 'charge paise');
  const parsedCashEffect = requireSafeInteger(
    cashEffectPaise,
    'cash effect paise',
    Number.MIN_SAFE_INTEGER
  );
  const gross = notionalPaise + parsedCharge;
  if (!Number.isSafeInteger(gross)) fail('cash effect paise must be a safe integer');
  const expectedCashEffect = side === 'buy' ? -gross : notionalPaise - parsedCharge;
  if (!Number.isSafeInteger(expectedCashEffect) || parsedCashEffect !== expectedCashEffect) {
    fail('cash effect paise is inconsistent with the draft');
  }
  return {
    draftId,
    side,
    exchange,
    symbolToken,
    tradingSymbol,
    quantity,
    pricePaise,
    quoteProvider,
    quoteTime,
    expiresAt,
    notionalPaise,
    chargePaise: parsedCharge,
    cashEffectPaise: parsedCashEffect,
    chargeStatus,
  };
}

export function decodePaperOrderDraft(value: unknown): PaperOrderDraft {
  if (!isRecord(value)) fail('draft must be an object');
  requireExactKeys(value, DRAFT_KEYS);
  if (value.version !== 1 || value.paper !== true) fail('draft has an unsupported version');
  return decodeDraftFields(
    {
      draftId: value.draft_id,
      side: value.side,
      exchange: value.exchange,
      symbolToken: value.symbol_token,
      tradingSymbol: value.trading_symbol,
      quantity: value.quantity,
      pricePaise: value.price_paise,
      quoteProvider: value.quote_provider,
      quoteTime: value.quote_time,
      expiresAt: value.expires_at,
      notionalPaise: value.notional_paise,
      chargePaise: value.charge_paise,
      cashEffectPaise: value.cash_effect_paise,
      chargeStatus: value.charge_status,
    },
    DRAFT_VALUE_KEYS
  );
}

export function assertPaperOrderDraft(value: unknown): PaperOrderDraft {
  return decodeDraftFields(value, DRAFT_VALUE_KEYS);
}

function decodeHolding(value: unknown): PaperHolding {
  if (!isRecord(value)) fail('holding must be an object');
  requireExactKeys(value, HOLDING_KEYS);
  const exchange = requireExchange(value.exchange);
  const symbolToken = requireSymbolToken(value.symbolToken);
  const tradingSymbol = requireText(value.tradingSymbol, 'trading symbol');
  const quantity = requireSafeInteger(value.quantity, 'holding quantity', 1);
  const costBasisPaise = requireSafeInteger(value.costBasisPaise, 'cost basis paise', 1);
  const averageCostPaise = requireSafeInteger(value.averageCostPaise, 'average cost paise', 1);
  if (averageCostPaise !== averageCost(costBasisPaise, quantity))
    fail('average cost is inconsistent');
  return { exchange, symbolToken, tradingSymbol, quantity, costBasisPaise, averageCostPaise };
}

function decodeFill(value: unknown): PaperFill {
  if (!isRecord(value)) fail('fill must be an object');
  requireExactKeys(value, FILL_KEYS);
  const draftId = requireText(value.draftId, 'draft id');
  const side = requireSide(value.side);
  const exchange = requireExchange(value.exchange);
  const symbolToken = requireSymbolToken(value.symbolToken);
  const tradingSymbol = requireText(value.tradingSymbol, 'trading symbol');
  const quantity = requireSafeInteger(value.quantity, 'fill quantity', 1);
  const fillPricePaise = requireSafeInteger(value.fillPricePaise, 'fill price paise', 1);
  const notionalPaise = requireSafeInteger(value.notionalPaise, 'notional paise');
  if (notionalPaise !== safeProduct(quantity, fillPricePaise, 'notional paise'))
    fail('fill notional is inconsistent');
  const chargesPaise = requireSafeInteger(value.chargesPaise, 'charges paise');
  const cashEffectPaise = requireSafeInteger(
    value.cashEffectPaise,
    'cash effect paise',
    Number.MIN_SAFE_INTEGER
  );
  const expectedCashEffect =
    side === 'buy' ? -(notionalPaise + chargesPaise) : notionalPaise - chargesPaise;
  if (!Number.isSafeInteger(expectedCashEffect) || cashEffectPaise !== expectedCashEffect) {
    fail('fill cash effect is inconsistent');
  }
  const realizedPnlPaise = requireSafeInteger(
    value.realizedPnlPaise,
    'realized P&L paise',
    Number.MIN_SAFE_INTEGER
  );
  if (side === 'buy' && realizedPnlPaise !== 0) fail('buy realized P&L must be zero');
  const filledAt = requireTimestamp(value.filledAt, 'fill time');
  return {
    draftId,
    side,
    exchange,
    symbolToken,
    tradingSymbol,
    quantity,
    fillPricePaise,
    notionalPaise,
    chargesPaise,
    cashEffectPaise,
    realizedPnlPaise,
    filledAt,
  };
}

export function decodePaperPortfolio(value: unknown): PaperPortfolio {
  if (!isRecord(value)) fail('portfolio must be an object');
  requireExactKeys(value, PORTFOLIO_KEYS);
  if (value.schemaVersion !== PAPER_PORTFOLIO_SCHEMA_VERSION)
    fail('unsupported portfolio schema version');
  if (value.startingCashPaise !== PAPER_STARTING_CASH_PAISE) fail('invalid starting cash');
  const portfolioId = requireText(value.portfolioId, 'portfolio id');
  const revision = requireSafeInteger(value.revision, 'revision');
  const cashPaise = requireSafeInteger(value.cashPaise, 'cash paise');
  if (
    !Array.isArray(value.holdings) ||
    !Array.isArray(value.fills) ||
    !Array.isArray(value.appliedDraftIds)
  ) {
    fail('portfolio collections must be arrays');
  }
  const holdings = value.holdings.map(decodeHolding);
  const holdingKeys = new Set(
    holdings.map((holding) => `${holding.exchange}:${holding.symbolToken}`)
  );
  if (holdingKeys.size !== holdings.length) fail('holdings must be unique');
  const fills = value.fills.map(decodeFill);
  const fillIds = fills.map((fill) => fill.draftId);
  if (new Set(fillIds).size !== fillIds.length) fail('fill draft ids must be unique');
  const appliedDraftIds = value.appliedDraftIds.map((draftId) =>
    requireText(draftId, 'applied draft id')
  );
  if (new Set(appliedDraftIds).size !== appliedDraftIds.length)
    fail('applied draft ids must be unique');
  if (
    appliedDraftIds.length !== fillIds.length ||
    appliedDraftIds.some((draftId) => !fillIds.includes(draftId))
  ) {
    fail('applied draft ids must match fills');
  }
  const createdAt = requireTimestamp(value.createdAt, 'created time');
  const updatedAt = requireTimestamp(value.updatedAt, 'updated time');
  return {
    schemaVersion: PAPER_PORTFOLIO_SCHEMA_VERSION,
    portfolioId,
    revision,
    startingCashPaise: PAPER_STARTING_CASH_PAISE,
    cashPaise,
    holdings,
    fills,
    appliedDraftIds,
    createdAt,
    updatedAt,
  };
}
