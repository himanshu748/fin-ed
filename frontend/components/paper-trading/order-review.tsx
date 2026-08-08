import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { animate } from 'animejs';
import { useReducedMotion } from 'motion/react';
import type { PaperLedgerReadiness } from '@/components/paper-trading/paper-trading-provider';
import {
  formatPaperCurrency,
  formatSignedPaperCurrency,
} from '@/components/paper-trading/portfolio-summary';
import type { PaperOrderDraft, PaperPortfolio } from '@/lib/paper-trading/types';

const quoteTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

const confirmLabels = {
  buy: 'Confirm paper buy',
  sell: 'Confirm paper sell',
} as const;

const FILLED_STATUS = 'Paper order filled in your practice portfolio.';

export function paperQuoteExpiry(expiresAt: string, nowMs: number) {
  const remainingMs = Date.parse(expiresAt) - nowMs;
  if (remainingMs <= 0) return { expired: true, label: 'Expired' } as const;
  const remainingSeconds = Math.ceil(remainingMs / 1_000);
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  return {
    expired: false,
    label: `Expires in ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`,
  } as const;
}

interface OrderReviewProps {
  draft: PaperOrderDraft | null;
  portfolio: PaperPortfolio;
  readiness: PaperLedgerReadiness;
  onConfirm(): Promise<boolean>;
}

function reviewError(
  draft: PaperOrderDraft,
  portfolio: PaperPortfolio,
  readiness: PaperLedgerReadiness,
  isExpired: boolean
): string | null {
  if (readiness !== 'ready') return 'Paper portfolio is unavailable.';
  if (isExpired) return 'Paper quote expired. Ask for a new quote.';
  if (
    draft.chargeStatus === 'unavailable' ||
    draft.chargePaise === null ||
    draft.cashEffectPaise === null
  ) {
    return 'Estimated charges unavailable. This draft cannot be confirmed.';
  }
  if (draft.side === 'buy' && portfolio.cashPaise < -draft.cashEffectPaise) {
    return 'Insufficient cash for paper buy.';
  }
  if (draft.side === 'sell') {
    const holding = portfolio.holdings.find(
      (candidate) =>
        candidate.exchange === draft.exchange && candidate.symbolToken === draft.symbolToken
    );
    if (!holding || holding.quantity < draft.quantity) {
      return 'Insufficient holdings for paper sell.';
    }
  }
  return null;
}

export function OrderReview({ draft, portfolio, readiness, onConfirm }: OrderReviewProps) {
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmationStatus, setConfirmationStatus] = useState<string | null>(null);
  const [confirmedDraftId, setConfirmedDraftId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const confirmationPathRef = useRef<SVGPathElement>(null);
  const animatedConfirmationIdRef = useRef<string | null>(null);
  const shouldReduceMotion = useReducedMotion();
  const draftExpiresAt = draft?.expiresAt;

  useEffect(() => {
    if (!draftExpiresAt) return;
    const expiresAtMs = Date.parse(draftExpiresAt);
    let active = true;
    let countdownTimer: ReturnType<typeof setTimeout> | null = null;

    const clearCountdownTimer = () => {
      if (countdownTimer === null) return;
      clearTimeout(countdownTimer);
      countdownTimer = null;
    };
    const refreshAndSchedule = () => {
      if (!active) return;
      clearCountdownTimer();
      const currentTime = Date.now();
      setNowMs(currentTime);
      if (document.hidden || currentTime >= expiresAtMs) return;
      const untilExpiry = expiresAtMs - currentTime;
      const remainingRemainder = untilExpiry % 1_000;
      const untilNextLabel = remainingRemainder === 0 ? 1_000 : remainingRemainder;
      countdownTimer = setTimeout(refreshAndSchedule, Math.min(untilNextLabel, untilExpiry));
    };

    document.addEventListener('visibilitychange', refreshAndSchedule);
    refreshAndSchedule();
    return () => {
      active = false;
      clearCountdownTimer();
      document.removeEventListener('visibilitychange', refreshAndSchedule);
    };
  }, [draftExpiresAt]);

  const showFillConfirmation =
    confirmationStatus === FILLED_STATUS &&
    confirmedDraftId !== null &&
    (!draft || confirmedDraftId === draft.draftId);

  useEffect(() => {
    const path = confirmationPathRef.current;
    if (!showFillConfirmation || !confirmedDraftId || !path) return;
    if (shouldReduceMotion || animatedConfirmationIdRef.current === confirmedDraftId) {
      path.style.strokeDashoffset = '0';
      return;
    }

    animatedConfirmationIdRef.current = confirmedDraftId;
    const pathLength = path.getTotalLength();
    path.style.strokeDasharray = String(pathLength);
    path.style.strokeDashoffset = String(pathLength);
    const animation = animate(path, {
      strokeDashoffset: [pathLength, 0],
      duration: 220,
      ease: 'out(3)',
    });

    return () => {
      animation.cancel();
      path.style.strokeDashoffset = '0';
    };
  }, [confirmedDraftId, shouldReduceMotion, showFillConfirmation]);

  const confirmationFeedback = (
    <div
      role="status"
      aria-live="polite"
      className="mt-2 flex min-h-6 items-center justify-center gap-2 text-center text-sm font-semibold"
    >
      {showFillConfirmation ? (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="size-5 shrink-0 text-[var(--banknote-green)]"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.25"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path ref={confirmationPathRef} d="M4.5 12.5 9 17l10.5-11" />
        </svg>
      ) : null}
      <span>{confirmationStatus}</span>
    </div>
  );

  if (!draft) {
    return (
      <section
        aria-labelledby="order-review-heading"
        className="rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] sm:p-6"
      >
        <h2 id="order-review-heading" className="font-display text-xl font-semibold">
          Order review
        </h2>
        <div className="mt-5 overflow-hidden rounded-[8px] border border-[var(--soft-rule)] bg-[var(--blue-wash)]">
          <Image
            src="/images/paper-practice-empty-v1.png"
            alt="Empty paper practice ledger"
            width={1536}
            height={1024}
            sizes="(min-width: 1024px) 24rem, 100vw"
            className="h-auto w-full"
          />
        </div>
        <p className="mt-5 font-semibold">No paper order to review</p>
        <p className="mt-2 text-sm leading-6 text-[var(--muted-ink)]">
          Ask FinEd Saathi to prepare an NSE equity practice order.
        </p>
        {confirmationFeedback}
      </section>
    );
  }

  const expiry = paperQuoteExpiry(draft.expiresAt, nowMs);
  const error = reviewError(draft, portfolio, readiness, expiry.expired);
  const charges = draft.chargePaise;
  const estimatedTotal = draft.cashEffectPaise === null ? null : Math.abs(draft.cashEffectPaise);
  const confirmLabel = confirmLabels[draft.side];
  const currentDraftId = draft.draftId;

  async function handleConfirm() {
    if (error || isConfirming) return;
    setIsConfirming(true);
    setConfirmationStatus(null);
    setConfirmedDraftId(null);
    const confirmed = await onConfirm();
    setConfirmationStatus(confirmed ? FILLED_STATUS : 'Paper order was not filled.');
    setConfirmedDraftId(confirmed ? currentDraftId : null);
    setIsConfirming(false);
  }

  return (
    <section
      aria-labelledby="order-review-heading"
      className="rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] sm:p-6"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 id="order-review-heading" className="font-display text-xl font-semibold">
          Review paper {draft.side}
        </h2>
        <span className="shrink-0 rounded-[8px] border border-dashed border-[var(--risk-brick)] px-3 py-2 text-sm font-semibold text-[var(--risk-brick)]">
          Not filled
        </span>
      </div>
      <p className="font-display mt-4 font-semibold">
        {draft.tradingSymbol} · {draft.exchange}
      </p>

      <dl className="mt-4 divide-y divide-[var(--soft-rule)] border-y border-[var(--ledger-rule)] text-sm">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Order type</dt>
          <dd>Market</dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Quantity</dt>
          <dd className="font-data tabular-nums">{draft.quantity}</dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Quote (last traded price)</dt>
          <dd className="font-data text-right tabular-nums">
            {formatPaperCurrency(draft.pricePaise)}
          </dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Notional</dt>
          <dd className="font-data text-right tabular-nums">
            {formatPaperCurrency(draft.notionalPaise)}
          </dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Estimated charges</dt>
          <dd className="font-data text-right tabular-nums">
            {charges === null ? 'Unavailable' : formatPaperCurrency(charges)}
          </dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Estimated total</dt>
          <dd className="font-data text-right tabular-nums">
            {estimatedTotal === null ? 'Unavailable' : formatPaperCurrency(estimatedTotal)}
          </dd>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3">
          <dt>Virtual cash effect</dt>
          <dd className="font-data text-right tabular-nums">
            {draft.cashEffectPaise === null
              ? 'Unavailable'
              : formatSignedPaperCurrency(draft.cashEffectPaise)}
          </dd>
        </div>
      </dl>

      <dl className="mt-4 grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-x-4 gap-y-3 text-sm">
        <dt>Quote source</dt>
        <dd className="font-data text-right break-words text-[var(--banknote-green)]">
          {draft.quoteProvider}
        </dd>
        <dt>Quote timestamp</dt>
        <dd className="font-data text-right text-xs">
          {quoteTimeFormatter.format(new Date(draft.quoteTime))}
        </dd>
        <dt>Quote expiry</dt>
        <dd className="text-right text-xs">
          <span className="font-data block">
            {quoteTimeFormatter.format(new Date(draft.expiresAt))}
          </span>
          <span
            className={`font-data mt-1 block font-semibold ${
              expiry.expired ? 'text-[var(--risk-brick)]' : 'text-[var(--ledger-blue)]'
            }`}
          >
            {expiry.label}
          </span>
        </dd>
      </dl>

      <div className="mt-5 rounded-[8px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] p-3 text-sm leading-6 text-[var(--ledger-blue)]">
        This is a simulated paper order. No real money or broker order will be used.
      </div>

      {error ? (
        <p role="alert" className="mt-3 text-sm font-semibold text-[var(--risk-brick)]">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        disabled={Boolean(error) || isConfirming}
        onClick={handleConfirm}
        className="mt-4 min-h-11 w-full min-w-11 rounded-[10px] bg-[var(--ledger-blue)] px-4 font-semibold text-white transition-colors hover:bg-[var(--ledger-blue-hover)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)] disabled:cursor-not-allowed disabled:bg-[var(--ledger-rule)] disabled:text-[var(--muted-ink)]"
      >
        {isConfirming ? 'Confirming paper order' : confirmLabel}
      </button>
      <p className="mt-2 text-center text-sm text-[var(--muted-ink)]">
        This updates only your practice portfolio.
      </p>
      {confirmationFeedback}
    </section>
  );
}
