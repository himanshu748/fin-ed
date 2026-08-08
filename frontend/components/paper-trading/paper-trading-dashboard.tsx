'use client';

import { useState } from 'react';
import { BookOpen, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { ActivityLedger } from '@/components/paper-trading/activity-ledger';
import { HoldingsLedger } from '@/components/paper-trading/holdings-ledger';
import { OrderReview } from '@/components/paper-trading/order-review';
import { usePaperTrading } from '@/components/paper-trading/paper-trading-provider';
import { PortfolioSummary } from '@/components/paper-trading/portfolio-summary';

export function PaperTradingDashboard() {
  const { readiness, portfolio, draft, error, closeDashboard, confirmDraft, resetPortfolio } =
    usePaperTrading();
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [resetStatus, setResetStatus] = useState<string | null>(null);

  async function handleReset() {
    if (readiness !== 'ready' || isResetting) return;
    setIsResetting(true);
    const reset = await resetPortfolio();
    setResetStatus(reset ? 'Practice portfolio reset.' : 'Practice portfolio could not be reset.');
    setIsResetting(false);
    if (reset) setIsResetOpen(false);
  }

  return (
    <main className="section-shell min-w-0 py-6 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--banknote-green)]">
            <ShieldCheck aria-hidden="true" className="size-5" />
            <span>Paper trading only</span>
          </div>
          <h1 className="font-display mt-3 text-3xl leading-tight font-bold sm:text-4xl">
            Practice portfolio
          </h1>
          <p className="mt-2 text-[var(--muted-ink)]">
            {new Intl.NumberFormat('en-IN', {
              style: 'currency',
              currency: 'INR',
              maximumFractionDigits: 0,
            }).format(portfolio.startingCashPaise / 100)}{' '}
            starting virtual cash. No real money or broker account.
          </p>
        </div>
        <button
          type="button"
          onClick={closeDashboard}
          className="flex min-h-11 min-w-11 items-center gap-2 rounded-[10px] border border-[var(--ledger-blue)] px-4 font-semibold text-[var(--ledger-blue)] transition-colors hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
        >
          <BookOpen aria-hidden="true" className="size-5" />
          Back to learning
        </button>
      </div>

      <div className="mt-6">
        <PortfolioSummary portfolio={portfolio} />
      </div>

      <div className="mt-7 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(19rem,0.85fr)] lg:items-start">
        <div className="min-w-0 lg:order-2">
          <OrderReview
            draft={draft}
            portfolio={portfolio}
            readiness={readiness}
            onConfirm={confirmDraft}
          />
        </div>
        <div className="min-w-0 space-y-8 lg:order-1">
          <HoldingsLedger holdings={portfolio.holdings} onBackToLearning={closeDashboard} />
          <ActivityLedger fills={portfolio.fills} />
        </div>
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--ledger-rule)] pt-5">
        <div role="status" aria-live="polite" className="min-h-6 text-sm text-[var(--muted-ink)]">
          {error ??
            resetStatus ??
            (readiness === 'ready' ? 'Paper ledger ready.' : 'Paper ledger unavailable.')}
        </div>
        <section aria-labelledby="paper-settings-heading" className="flex items-center gap-2">
          <h2
            id="paper-settings-heading"
            className="font-data text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase"
          >
            Settings
          </h2>
          <button
            type="button"
            disabled={readiness !== 'ready' || isResetting}
            onClick={() => setIsResetOpen(true)}
            className="flex min-h-11 min-w-11 items-center gap-2 rounded-[10px] px-3 font-semibold text-[var(--ledger-blue)] transition-colors hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)] disabled:cursor-not-allowed disabled:text-[var(--muted-ink)]"
          >
            <RotateCcw aria-hidden="true" className="size-5" />
            Reset practice
          </button>
        </section>
      </div>

      {isResetOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-practice-title"
          aria-describedby="reset-practice-description"
          className="fixed inset-0 z-50 grid place-items-center bg-[rgb(21_35_59/0.45)] p-4"
        >
          <section className="w-full max-w-md rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] shadow-xl sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="reset-practice-title" className="font-display text-xl font-semibold">
                  Reset practice portfolio?
                </h2>
                <p
                  id="reset-practice-description"
                  className="mt-3 text-sm leading-6 text-[var(--muted-ink)]"
                >
                  This clears all paper holdings and fill activity, then restores the original
                  virtual cash balance. Your live voice session stays connected.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close reset confirmation"
                onClick={() => setIsResetOpen(false)}
                className="grid min-h-11 min-w-11 shrink-0 place-items-center rounded-[10px] text-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            </div>
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setIsResetOpen(false)}
                className="min-h-11 min-w-11 rounded-[10px] border border-[var(--ledger-blue)] px-4 font-semibold text-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
              >
                Keep practice portfolio
              </button>
              <button
                type="button"
                disabled={isResetting}
                onClick={handleReset}
                className="min-h-11 min-w-11 rounded-[10px] bg-[var(--ledger-blue)] px-4 font-semibold text-white hover:bg-[var(--ledger-blue-hover)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)] disabled:cursor-not-allowed disabled:bg-[var(--ledger-rule)] disabled:text-[var(--muted-ink)]"
              >
                {isResetting ? 'Resetting practice' : 'Confirm reset practice'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
