'use client';

import { useId } from 'react';
import { LEARNING_MODES, type LearningMode } from '@/lib/learning-modes';
import { cn } from '@/lib/shadcn/utils';

const CARD_SPANS: Record<LearningMode, string> = {
  stocks: 'sm:col-span-3 lg:col-span-5',
  mutual_funds: 'sm:col-span-3 lg:col-span-7',
  etfs: 'sm:col-span-2 lg:col-span-4',
  gold: 'sm:col-span-4 lg:col-span-5',
  fno: 'sm:col-span-3 lg:col-span-3',
  ipos: 'sm:col-span-3 lg:col-span-5',
  bonds: 'sm:col-span-2 lg:col-span-3',
  general: 'sm:col-span-4 lg:col-span-4',
};

const MODE_KEYS: Record<LearningMode, string> = {
  stocks: 'EQUITY',
  mutual_funds: 'MONTHLY',
  etfs: 'EXCHANGE',
  gold: 'METAL',
  fno: 'RISK',
  ipos: 'PRIMARY',
  bonds: 'DEBT',
  general: 'OPEN',
};

const FNO_RISK_COPY =
  'F&O can create rapid and substantial losses. This mode teaches mechanics and risk only. It does not provide calls or strategies for a live trade.';

function ModeGraphic({ mode }: { mode: LearningMode }) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    strokeWidth: 1.6,
  };

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 72 48"
      className="h-12 w-[4.5rem] text-[var(--ledger-blue)]"
    >
      {mode === 'stocks' && (
        <g {...common}>
          <rect x="7" y="7" width="44" height="34" rx="4" />
          <path d="M14 15H43M14 21H43M14 30H29M14 35H25" />
          <path d="M51 16H65V41H37V35" />
        </g>
      )}
      {mode === 'mutual_funds' && (
        <g {...common}>
          <path d="M8 10H28M8 19H32M8 28H25" />
          <path d="M36 8V34M43 13V34M50 18V34" />
          <path d="M31 34H58L54 42H35L31 34Z" />
          <path d="M25 28L36 34" />
        </g>
      )}
      {mode === 'etfs' && (
        <g {...common}>
          <path d="M8 12H64M8 36H64" />
          <rect x="21" y="17" width="8" height="8" rx="1" />
          <rect x="32" y="17" width="8" height="8" rx="1" />
          <rect x="43" y="17" width="8" height="8" rx="1" />
          <path d="M16 30H56M51 26L56 30L51 34" />
        </g>
      )}
      {mode === 'gold' && (
        <g {...common}>
          <circle cx="23" cy="24" r="13" />
          <circle cx="23" cy="24" r="7" />
          <path d="M42 10H63V39H42V10ZM47 17H58M47 23H58M47 29H55" />
        </g>
      )}
      {mode === 'fno' && (
        <g {...common}>
          <path d="M7 39H65M11 8V39" />
          <path d="M13 31L27 24L38 29L57 10" />
          <path d="M38 29L58 39" stroke="#A13D35" />
          <path d="M53 10H57V14" />
        </g>
      )}
      {mode === 'ipos' && (
        <g {...common}>
          <rect x="8" y="6" width="34" height="36" rx="3" />
          <path d="M15 14H35M15 21H35M15 29H25" />
          <path d="M48 13H64V27H48V13ZM46 35H55M59 35H66" />
          <path d="M42 24L48 20" />
        </g>
      )}
      {mode === 'bonds' && (
        <g {...common}>
          <path d="M8 13H63M8 35H63" />
          <path d="M14 8V40M57 8V40" />
          <circle cx="25" cy="24" r="5" />
          <path d="M35 19H50M35 24H50M35 29H45" />
        </g>
      )}
      {mode === 'general' && (
        <g {...common}>
          <path d="M8 14V34M14 9V39M20 17V31M26 12V36" />
          <path d="M37 8H64V40H37C33.6863 40 31 37.3137 31 34V14C31 10.6863 33.6863 8 37 8Z" />
          <path d="M40 17H56M40 24H59M40 31H53" />
        </g>
      )}
    </svg>
  );
}

interface ModeBentoProps {
  value: LearningMode;
  onChange: (value: LearningMode) => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function ModeBento({
  value,
  onChange,
  disabled = false,
  disabledReason = 'Mode locked for this call',
}: ModeBentoProps) {
  const riskId = useId();

  return (
    <div>
      <div
        role="radiogroup"
        aria-label="Choose a market learning mode"
        aria-describedby={disabled ? `${riskId}-locked` : undefined}
        className="grid grid-cols-1 gap-3 sm:grid-cols-6 lg:grid-cols-12"
      >
        {LEARNING_MODES.map((mode) => {
          const isSelected = value === mode.value;
          const isRiskMode = mode.value === 'fno';

          return (
            <label
              key={mode.value}
              data-mode={mode.value}
              className={cn(
                'relative flex min-h-44 cursor-pointer flex-col justify-between overflow-hidden rounded-[12px] border bg-[var(--surface)] p-[18px] transition-[transform,border-color,background-color] duration-200 ease-out sm:p-6',
                CARD_SPANS[mode.value],
                isSelected
                  ? 'border-[var(--ledger-blue)] bg-[var(--blue-wash)]'
                  : 'border-[var(--ledger-rule)] hover:-translate-y-[3px] hover:border-[var(--ledger-blue)]',
                disabled && 'cursor-not-allowed opacity-55 hover:translate-y-0'
              )}
            >
              <input
                type="radio"
                role="radio"
                name="learning-mode"
                value={mode.value}
                checked={isSelected}
                aria-checked={isSelected}
                aria-describedby={isRiskMode && isSelected ? riskId : undefined}
                disabled={disabled}
                onChange={() => onChange(mode.value)}
                className="peer absolute inset-0 size-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
              />
              <div className="pointer-events-none flex items-start justify-between gap-4">
                <ModeGraphic mode={mode.value} />
                <span className="font-data rounded-[6px] border border-[var(--soft-rule)] bg-[var(--paper)] px-2 py-1 text-[0.64rem] tracking-[0.08em] text-[var(--muted-ink)]">
                  {MODE_KEYS[mode.value]}
                </span>
              </div>
              <div className="pointer-events-none mt-5">
                <h3 className="font-display text-xl font-semibold text-[var(--ledger-ink)]">
                  {mode.label}
                </h3>
                <p className="mt-1 text-sm leading-6 text-[var(--muted-ink)]">{mode.helper}</p>
              </div>
              <span className="pointer-events-none absolute inset-0 rounded-[12px] peer-focus-visible:outline-3 peer-focus-visible:outline-offset-[-3px] peer-focus-visible:outline-[var(--ledger-blue)]" />
            </label>
          );
        })}
      </div>

      {value === 'fno' && (
        <div
          id={riskId}
          role="note"
          className="mt-4 rounded-[12px] border border-[var(--risk-brick)] bg-[var(--risk-wash)] p-[18px] text-sm leading-6 text-[var(--risk-brick)] sm:p-6"
        >
          <strong className="font-display font-semibold">Risk boundary:</strong> {FNO_RISK_COPY}
        </div>
      )}

      {disabled && (
        <p id={`${riskId}-locked`} className="mt-3 text-sm text-[var(--muted-ink)]">
          {disabledReason}
        </p>
      )}
    </div>
  );
}
