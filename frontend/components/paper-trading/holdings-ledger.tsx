import { formatPaperCurrency } from '@/components/paper-trading/portfolio-summary';
import type { PaperHolding } from '@/lib/paper-trading/types';

interface HoldingsLedgerProps {
  holdings: PaperHolding[];
  onBackToLearning(): void;
}

export function HoldingsLedger({ holdings, onBackToLearning }: HoldingsLedgerProps) {
  return (
    <section aria-labelledby="holdings-heading" className="min-w-0">
      <div className="border-b border-[var(--ledger-rule)] px-1 pb-3">
        <h2 id="holdings-heading" className="font-display text-xl font-semibold">
          Holdings
        </h2>
        <p className="mt-1 text-sm text-[var(--muted-ink)]">
          Recorded quantities and historical cost only.
        </p>
      </div>

      {holdings.length === 0 ? (
        <div className="grid min-h-64 place-items-center border-x border-b border-[var(--ledger-rule)] bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,var(--soft-rule)_32px)] px-[18px] py-10 text-center">
          <div>
            <h3 className="font-display text-lg font-semibold">No paper holdings yet</h3>
            <p className="mt-2 text-sm leading-6 text-[var(--muted-ink)]">
              Ask FinEd Saathi to prepare an NSE equity paper order.
            </p>
            <button
              type="button"
              onClick={onBackToLearning}
              className="mt-4 min-h-11 min-w-11 rounded-[10px] px-3 font-semibold text-[var(--ledger-blue)] transition-colors hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
            >
              Back to learning
            </button>
          </div>
        </div>
      ) : (
        <>
          <table className="hidden w-full table-fixed border-collapse text-left text-sm md:table [&_td]:px-3 [&_td]:py-4 [&_th]:px-3 [&_th]:py-3">
            <caption className="sr-only">
              Paper holdings recorded at historical cost. Current values are unavailable.
            </caption>
            <thead>
              <tr className="border-b border-[var(--ledger-rule)] text-xs tracking-[0.04em] text-[var(--muted-ink)]">
                <th scope="col">Instrument</th>
                <th scope="col">Quantity</th>
                <th scope="col">Average cost</th>
                <th scope="col">Historical cost basis</th>
                <th scope="col">Current/live value</th>
                <th scope="col">Unrealized P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => (
                <tr
                  key={`${holding.exchange}:${holding.symbolToken}`}
                  className="border-b border-[var(--soft-rule)] align-top"
                >
                  <td>
                    <span className="block font-semibold">{holding.tradingSymbol}</span>
                    <span className="font-data text-xs text-[var(--muted-ink)]">
                      {holding.exchange}
                    </span>
                  </td>
                  <td className="font-data tabular-nums">{holding.quantity}</td>
                  <td className="font-data tabular-nums">
                    {formatPaperCurrency(holding.averageCostPaise)}
                  </td>
                  <td className="font-data tabular-nums">
                    {formatPaperCurrency(holding.costBasisPaise)}
                  </td>
                  <td className="font-semibold text-[var(--risk-brick)]">Unavailable</td>
                  <td className="font-semibold text-[var(--risk-brick)]">Unavailable</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="divide-y divide-[var(--soft-rule)] border-x border-b border-[var(--ledger-rule)] md:hidden">
            {holdings.map((holding) => (
              <article
                key={`${holding.exchange}:${holding.symbolToken}`}
                className="bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,var(--soft-rule)_32px)] px-[18px] py-5"
                aria-label={`${holding.tradingSymbol} holding`}
              >
                <h3 className="font-display font-semibold">{holding.tradingSymbol}</h3>
                <p className="font-data mt-1 text-xs text-[var(--muted-ink)]">{holding.exchange}</p>
                <dl className="mt-4 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-3 text-sm">
                  <dt>Quantity</dt>
                  <dd className="font-data text-right tabular-nums">{holding.quantity}</dd>
                  <dt>Average cost</dt>
                  <dd className="font-data text-right tabular-nums">
                    {formatPaperCurrency(holding.averageCostPaise)}
                  </dd>
                  <dt>Historical cost basis</dt>
                  <dd className="font-data text-right tabular-nums">
                    {formatPaperCurrency(holding.costBasisPaise)}
                  </dd>
                  <dt>Current/live value</dt>
                  <dd className="font-semibold text-[var(--risk-brick)]">Unavailable</dd>
                  <dt>Unrealized P&amp;L</dt>
                  <dd className="font-semibold text-[var(--risk-brick)]">Unavailable</dd>
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
