import { decodePaperPortfolio } from './schema';
import type {
  LoadResult,
  PaperPortfolio,
  PaperPortfolioLockCoordinator,
  PaperPortfolioStorage,
  SavePaperPortfolioOptions,
  SaveResult,
} from './types';

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
  return existing.revision >= candidate.revision;
}

function browserLockCoordinator(): PaperPortfolioLockCoordinator | null {
  const browser = globalThis as {
    navigator?: { locks?: PaperPortfolioLockCoordinator };
  };
  const locks = browser.navigator?.locks;
  return locks && typeof locks.request === 'function' ? locks : null;
}

function saveWithinExclusiveLock(
  storage: PaperPortfolioStorage | null | undefined,
  candidate: PaperPortfolio,
  options: SavePaperPortfolioOptions
): SaveResult {
  if (options.canCommit && !options.canCommit()) {
    return { status: 'aborted', reason: 'commit-precondition' };
  }
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

export async function savePaperPortfolio(
  storage: PaperPortfolioStorage | null | undefined,
  portfolio: PaperPortfolio,
  coordinator: PaperPortfolioLockCoordinator | null | undefined = undefined,
  options: SavePaperPortfolioOptions = {}
): Promise<SaveResult> {
  const candidate = decodePaperPortfolio(portfolio);
  const locks = coordinator === undefined ? browserLockCoordinator() : coordinator;
  if (!locks || typeof locks.request !== 'function') return { status: 'unavailable' };
  try {
    return await locks.request(PAPER_PORTFOLIO_STORAGE_KEY, { mode: 'exclusive' }, () =>
      saveWithinExclusiveLock(storage, candidate, options)
    );
  } catch {
    return { status: 'unavailable' };
  }
}
