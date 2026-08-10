'use client';

import { useAnimatedNumber } from '@/hooks/use-animated-number';
import type { PaperPortfolio } from '@/lib/paper-trading/types';
import { type PaperHoldingQuotes, paperPortfolioValuation } from '@/lib/paper-trading/valuation';

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatPaperCurrency(paise: number): string {
  return currencyFormatter.format(paise / 100);
}

export function formatSignedPaperCurrency(paise: number): string {
  const sign = paise < 0 ? '−' : '+';
  return `${sign}${formatPaperCurrency(Math.abs(paise))}`;
}

interface PortfolioSummaryProps {
  portfolio: PaperPortfolio;
  holdingQuotes: PaperHoldingQuotes;
  quoteStatus: 'idle' | 'loading' | 'ready' | 'partial' | 'unavailable';
}

export function PortfolioSummary({ portfolio, holdingQuotes, quoteStatus }: PortfolioSummaryProps) {
  const holdingsCostBasisPaise = portfolio.holdings.reduce(
    (total, holding) => total + holding.costBasisPaise,
    0
  );
  const realizedPnlPaise = portfolio.fills.reduce(
    (total, fill) => total + fill.realizedPnlPaise,
    0
  );
  const animatedCashPaise = useAnimatedNumber(portfolio.cashPaise);
  const animatedHoldingsCostBasisPaise = useAnimatedNumber(holdingsCostBasisPaise);
  const valuation = paperPortfolioValuation(portfolio.holdings, holdingQuotes);

  return (
    <section aria-labelledby="portfolio-summary-heading">
      <h2 id="portfolio-summary-heading" className="sr-only">
        Portfolio summary
      </h2>
      <dl className="grid overflow-hidden rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] sm:grid-cols-3">
        <div className="border-b border-[var(--soft-rule)] px-[18px] py-5 sm:border-r sm:border-b-0 sm:px-6">
          <dt className="text-sm text-[var(--muted-ink)]">Virtual cash</dt>
          <dd
            aria-label={`Virtual cash: ${formatPaperCurrency(portfolio.cashPaise)}`}
            className="font-data mt-2 text-xl tabular-nums sm:text-2xl"
          >
            <span aria-hidden="true">{formatPaperCurrency(animatedCashPaise)}</span>
          </dd>
        </div>
        <div className="border-b border-[var(--soft-rule)] px-[18px] py-5 sm:border-r sm:border-b-0 sm:px-6">
          <dt className="text-sm text-[var(--muted-ink)]">Holdings historical cost basis</dt>
          <dd
            aria-label={`Holdings historical cost basis: ${formatPaperCurrency(holdingsCostBasisPaise)}`}
            className="font-data mt-2 text-xl tabular-nums sm:text-2xl"
          >
            <span aria-hidden="true">{formatPaperCurrency(animatedHoldingsCostBasisPaise)}</span>
          </dd>
        </div>
        <div className="px-[18px] py-5 sm:px-6">
          <dt className="text-sm text-[var(--muted-ink)]">Realized P&amp;L</dt>
          <dd
            className={`font-data mt-2 text-xl tabular-nums sm:text-2xl ${
              realizedPnlPaise < 0 ? 'text-[var(--risk-brick)]' : 'text-[var(--ledger-ink)]'
            }`}
          >
            {formatSignedPaperCurrency(realizedPnlPaise)}
          </dd>
        </div>
      </dl>
      <p
        role="status"
        aria-live="polite"
        className="mt-3 flex items-start gap-2 text-sm leading-6 text-[var(--muted-ink)]"
      >
        <span aria-hidden="true" className="font-data text-[var(--ledger-blue)]">
          i
        </span>
        {portfolio.holdings.length === 0 ? (
          <span>Current/live value: no confirmed paper holdings to value yet.</span>
        ) : valuation.complete ? (
          <span>
            Current holdings value:{' '}
            <strong className="text-[var(--ledger-ink)]">
              {formatPaperCurrency(valuation.marketValuePaise)}
            </strong>
            . Unrealized P&amp;L:{' '}
            <strong
              className={
                valuation.unrealizedPnlPaise < 0
                  ? 'text-[var(--risk-brick)]'
                  : 'text-[var(--banknote-green)]'
              }
            >
              {formatSignedPaperCurrency(valuation.unrealizedPnlPaise)}
            </strong>
            . Trusted Angel One quote refreshed every 30 seconds while this dashboard is open.
          </span>
        ) : quoteStatus === 'loading' ? (
          <span>Current/live value: fetching trusted Angel One quotes.</span>
        ) : (
          <span>
            Current/live value: <strong className="text-[var(--risk-brick)]">Unavailable</strong>{' '}
            for one or more holdings. Try refreshing the trusted quotes.
          </span>
        )}
      </p>
    </section>
  );
}
