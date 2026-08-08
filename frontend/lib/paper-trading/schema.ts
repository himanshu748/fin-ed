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
const PAPER_TIMESTAMP =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-](\d{2}):(\d{2}))$/;

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

export function isPaperTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = PAPER_TIMESTAMP.exec(value);
  if (!match) return false;
  const [
    ,
    yearText,
    monthText,
    dayText,
    hourText,
    minuteText,
    secondText,
    ,
    zone,
    offsetHourText,
    offsetMinuteText,
  ] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const offsetHour = offsetHourText === undefined ? 0 : Number(offsetHourText);
  const offsetMinute = offsetMinuteText === undefined ? 0 : Number(offsetMinuteText);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return (
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= daysInMonth[month - 1] &&
    hour <= 23 &&
    minute <= 59 &&
    second <= 59 &&
    (zone === 'Z' || (offsetHour <= 23 && offsetMinute <= 59)) &&
    Number.isFinite(Date.parse(value))
  );
}

function timestampFractionMicros(value: string): number {
  const match = PAPER_TIMESTAMP.exec(value);
  if (!match) fail('timestamp must be an ISO timestamp');
  return Number((match[7] ?? '').padEnd(6, '0'));
}

function requireTimestamp(value: unknown, field: string): string {
  if (!isPaperTimestamp(value)) {
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

function safeSum(left: number, right: number, field: string): number {
  const sum = left + right;
  if (!Number.isSafeInteger(sum)) fail(`${field} must be a safe integer`);
  return sum;
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
  if (
    Date.parse(expiresAt) - Date.parse(quoteTime) !== 30_000 ||
    timestampFractionMicros(expiresAt) !== timestampFractionMicros(quoteTime)
  )
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

function holdingIndex(
  holdings: readonly PaperHolding[],
  exchange: string,
  symbolToken: string
): number {
  return holdings.findIndex(
    (holding) => holding.exchange === exchange && holding.symbolToken === symbolToken
  );
}

function holdingsMatch(left: readonly PaperHolding[], right: readonly PaperHolding[]): boolean {
  return (
    left.length === right.length &&
    left.every(
      (holding, index) =>
        holding.exchange === right[index].exchange &&
        holding.symbolToken === right[index].symbolToken &&
        holding.tradingSymbol === right[index].tradingSymbol &&
        holding.quantity === right[index].quantity &&
        holding.costBasisPaise === right[index].costBasisPaise &&
        holding.averageCostPaise === right[index].averageCostPaise
    )
  );
}

function replayFills(fills: readonly PaperFill[]): {
  cashPaise: number;
  holdings: PaperHolding[];
} {
  let cashPaise: number = PAPER_STARTING_CASH_PAISE;
  let holdings: PaperHolding[] = [];
  for (const fill of fills) {
    if (fill.exchange !== 'NSE') fail('paper fills are limited to NSE');
    cashPaise = safeSum(cashPaise, fill.cashEffectPaise, 'cash paise');
    if (cashPaise < 0) fail('fill requires unavailable cash');
    const index = holdingIndex(holdings, fill.exchange, fill.symbolToken);
    const current = index < 0 ? undefined : holdings[index];
    if (fill.side === 'buy') {
      const quantity = safeSum(current?.quantity ?? 0, fill.quantity, 'holding quantity');
      const costBasisPaise = safeSum(
        safeSum(current?.costBasisPaise ?? 0, fill.notionalPaise, 'cost basis paise'),
        fill.chargesPaise,
        'cost basis paise'
      );
      const next: PaperHolding = {
        exchange: fill.exchange,
        symbolToken: fill.symbolToken,
        tradingSymbol: fill.tradingSymbol,
        quantity,
        costBasisPaise,
        averageCostPaise: averageCost(costBasisPaise, quantity),
      };
      holdings = current
        ? holdings.map((holding, holdingIndex) => (holdingIndex === index ? next : holding))
        : [...holdings, next];
      continue;
    }
    if (!current || current.quantity < fill.quantity) fail('sell requires unavailable holdings');
    const costSoldPaise = Math.floor(
      safeProduct(current.costBasisPaise, fill.quantity, 'sold cost basis paise') / current.quantity
    );
    if (!Number.isSafeInteger(costSoldPaise)) fail('sold cost basis paise must be a safe integer');
    const realizedPnlPaise = safeSum(fill.cashEffectPaise, -costSoldPaise, 'realized P&L paise');
    if (fill.realizedPnlPaise !== realizedPnlPaise) fail('recorded realized P&L is inconsistent');
    const quantity = current.quantity - fill.quantity;
    if (quantity === 0) {
      holdings = holdings.filter((_, holdingIndex) => holdingIndex !== index);
      continue;
    }
    const costBasisPaise = safeSum(current.costBasisPaise, -costSoldPaise, 'cost basis paise');
    const next: PaperHolding = {
      ...current,
      quantity,
      costBasisPaise,
      averageCostPaise: averageCost(costBasisPaise, quantity),
    };
    holdings = holdings.map((holding, holdingIndex) => (holdingIndex === index ? next : holding));
  }
  return { cashPaise, holdings };
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
    appliedDraftIds.some((draftId, index) => draftId !== fillIds[index])
  ) {
    fail('applied draft ids must match fills');
  }
  const replayed = replayFills(fills);
  if (cashPaise !== replayed.cashPaise) fail('cash paise is inconsistent with fills');
  if (!holdingsMatch(holdings, replayed.holdings)) fail('holdings are inconsistent with fills');
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
