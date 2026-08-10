import type { PaperHolding } from './types';

const MAX_RPC_PAYLOAD_BYTES = 15_000;
const MAX_PAPER_HOLDINGS = 25;
const QUOTE_METHOD = 'fined.paper.v1.quote_holdings';
const QUOTE_TIMEOUT_MS = 10_000;
const QUOTE_KEYS = [
  'exchange',
  'symbol_token',
  'trading_symbol',
  'price_paise',
  'quote_time',
  'provider',
] as const;

export interface PaperHoldingQuote {
  exchange: string;
  symbolToken: string;
  tradingSymbol: string;
  pricePaise: number;
  quoteTime: string;
  provider: string;
}

export type PaperHoldingQuotes = Record<string, PaperHoldingQuote>;

export interface PaperPortfolioValuation {
  marketValuePaise: number;
  unrealizedPnlPaise: number;
  quoteCount: number;
  complete: boolean;
  latestQuoteTime: string | null;
}

interface PaperQuoteRpcSender {
  performRpc(options: {
    destinationIdentity: string;
    method: string;
    payload: string;
    responseTimeout: number;
  }): Promise<string>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireExactKeys(value: Record<string, unknown>, expected: readonly string[]): void {
  const actual = Object.keys(value);
  if (actual.length !== expected.length || actual.some((key) => !expected.includes(key))) {
    throw new Error('Paper quote payload has an invalid shape');
  }
}

function requireText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`Paper quote ${field} must be non-empty text`);
  }
  return value;
}

function requireExchange(value: unknown): string {
  if (value !== 'NSE' && value !== 'BSE') throw new Error('Paper quote exchange is invalid');
  return value;
}

function requireToken(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{1,20}$/.test(value)) {
    throw new Error('Paper quote symbol token is invalid');
  }
  return value;
}

function requireTimestamp(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new Error('Paper quote timestamp is invalid');
  }
  return value;
}

export function paperHoldingKey(holding: Pick<PaperHolding, 'exchange' | 'symbolToken'>): string {
  return `${holding.exchange}:${holding.symbolToken}`;
}

export function decodePaperHoldingQuotes(payload: string): PaperHoldingQuotes {
  if (
    typeof payload !== 'string' ||
    new TextEncoder().encode(payload).byteLength > MAX_RPC_PAYLOAD_BYTES
  ) {
    throw new Error('Paper quote payload exceeds the maximum size');
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    throw new Error('Paper quote payload must be valid JSON');
  }
  if (!isRecord(decoded)) throw new Error('Paper quote payload must be an object');
  requireExactKeys(decoded, ['version', 'paper', 'quotes']);
  if (decoded.version !== 1 || decoded.paper !== true || !Array.isArray(decoded.quotes)) {
    throw new Error('Paper quote payload is unsupported');
  }
  if (decoded.quotes.length > MAX_PAPER_HOLDINGS) {
    throw new Error('Paper quote payload contains too many quotes');
  }
  const quotes: PaperHoldingQuotes = {};
  for (const raw of decoded.quotes) {
    if (!isRecord(raw)) throw new Error('Paper quote must be an object');
    requireExactKeys(raw, QUOTE_KEYS);
    const exchange = requireExchange(raw.exchange);
    const symbolToken = requireToken(raw.symbol_token);
    const pricePaise = raw.price_paise;
    if (!Number.isSafeInteger(pricePaise) || (pricePaise as number) <= 0) {
      throw new Error('Paper quote price must be positive whole paise');
    }
    const quote: PaperHoldingQuote = {
      exchange,
      symbolToken,
      tradingSymbol: requireText(raw.trading_symbol, 'trading symbol'),
      pricePaise: pricePaise as number,
      quoteTime: requireTimestamp(raw.quote_time),
      provider: requireText(raw.provider, 'provider'),
    };
    const key = paperHoldingKey(quote);
    if (quotes[key]) throw new Error('Paper quote payload contains a duplicate quote');
    quotes[key] = quote;
  }
  return quotes;
}

export function paperPortfolioValuation(
  holdings: PaperHolding[],
  quotes: PaperHoldingQuotes
): PaperPortfolioValuation {
  let marketValuePaise = 0;
  let quotedCostBasisPaise = 0;
  let quoteCount = 0;
  let latestQuoteTime: string | null = null;
  for (const holding of holdings) {
    const quote = quotes[paperHoldingKey(holding)];
    if (!quote) continue;
    const value = holding.quantity * quote.pricePaise;
    if (!Number.isSafeInteger(value)) throw new Error('Paper market value exceeds safe limits');
    marketValuePaise += value;
    quotedCostBasisPaise += holding.costBasisPaise;
    if (!Number.isSafeInteger(marketValuePaise) || !Number.isSafeInteger(quotedCostBasisPaise)) {
      throw new Error('Paper market value exceeds safe limits');
    }
    quoteCount += 1;
    if (latestQuoteTime === null || Date.parse(quote.quoteTime) > Date.parse(latestQuoteTime)) {
      latestQuoteTime = quote.quoteTime;
    }
  }
  return {
    marketValuePaise,
    unrealizedPnlPaise: marketValuePaise - quotedCostBasisPaise,
    quoteCount,
    complete: holdings.length > 0 && quoteCount === holdings.length,
    latestQuoteTime,
  };
}

export async function requestPaperHoldingQuotes(
  participant: PaperQuoteRpcSender,
  agentIdentity: string,
  holdings: PaperHolding[]
): Promise<PaperHoldingQuotes> {
  if (!agentIdentity.trim()) throw new Error('Connected agent identity is required');
  if (!holdings.length || holdings.length > MAX_PAPER_HOLDINGS) {
    throw new Error('Paper quote request must contain 1 to 25 holdings');
  }
  const payload = JSON.stringify({
    version: 1,
    paper: true,
    holdings: holdings.map((holding) => ({
      exchange: holding.exchange,
      symbol_token: holding.symbolToken,
      trading_symbol: holding.tradingSymbol,
      quantity: holding.quantity,
    })),
  });
  if (new TextEncoder().encode(payload).byteLength > MAX_RPC_PAYLOAD_BYTES) {
    throw new Error('Paper quote request exceeds the maximum size');
  }
  const response = await participant.performRpc({
    destinationIdentity: agentIdentity,
    method: QUOTE_METHOD,
    payload,
    responseTimeout: QUOTE_TIMEOUT_MS,
  });
  return decodePaperHoldingQuotes(response);
}
