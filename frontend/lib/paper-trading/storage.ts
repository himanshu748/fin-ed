import { decodePaperPortfolio } from './schema';
import type { LoadResult, PaperPortfolio, PaperPortfolioStorage, SaveResult } from './types';

export const PAPER_PORTFOLIO_STORAGE_KEY = 'fined.paper.portfolio.v1';

export function loadPaperPortfolio(storage: PaperPortfolioStorage | null | undefined): LoadResult {
  if (!storage || typeof storage.getItem !== 'function') return { status: 'unavailable' };
  let raw: string | null;
  try {
    raw = storage.getItem(PAPER_PORTFOLIO_STORAGE_KEY);
  } catch {
    return { status: 'unavailable' };
  }
  if (raw === null) return { status: 'missing' };
  if (typeof raw !== 'string') return { status: 'corrupt', raw: null };
  try {
    return { status: 'ready', portfolio: decodePaperPortfolio(JSON.parse(raw)) };
  } catch {
    return { status: 'corrupt', raw };
  }
}

function existingWins(existing: PaperPortfolio, candidate: PaperPortfolio): boolean {
  if (existing.revision !== candidate.revision) return existing.revision > candidate.revision;
  return Date.parse(existing.updatedAt) >= Date.parse(candidate.updatedAt);
}

export function savePaperPortfolio(
  storage: PaperPortfolioStorage | null | undefined,
  portfolio: PaperPortfolio
): SaveResult {
  const candidate = decodePaperPortfolio(portfolio);
  const current = loadPaperPortfolio(storage);
  if (current.status === 'unavailable' || current.status === 'corrupt') return current;
  if (current.status === 'ready' && existingWins(current.portfolio, candidate)) {
    return { status: 'stale', portfolio: current.portfolio };
  }
  if (!storage || typeof storage.setItem !== 'function') return { status: 'unavailable' };
  try {
    storage.setItem(PAPER_PORTFOLIO_STORAGE_KEY, JSON.stringify(candidate));
  } catch {
    return { status: 'unavailable' };
  }
  return { status: 'saved', portfolio: candidate };
}
