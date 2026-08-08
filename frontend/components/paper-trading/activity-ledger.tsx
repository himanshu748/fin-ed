import {
  formatPaperCurrency,
  formatSignedPaperCurrency,
} from '@/components/paper-trading/portfolio-summary';
import type { PaperFill } from '@/lib/paper-trading/types';

const dateFormatter = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

interface ActivityLedgerProps {
  fills: PaperFill[];
}

function fillDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

export function ActivityLedger({ fills }: ActivityLedgerProps) {
  return (
    <section aria-labelledby="activity-heading" className="min-w-0">
      <div className="border-b border-[var(--ledger-rule)] px-1 pb-3">
        <h2 id="activity-heading" className="font-display text-xl font-semibold">
          Activity
        </h2>
        <p className="mt-1 text-sm text-[var(--muted-ink)]">
          Simulated fills recorded in this browser.
        </p>
      </div>

      {fills.length === 0 ? (
        <div className="grid min-h-40 place-items-center border-x border-b border-[var(--ledger-rule)] bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,var(--soft-rule)_32px)] px-[18px] py-8 text-center">
          <div>
            <h3 className="font-display font-semibold">No paper fills yet</h3>
            <p className="mt-2 text-sm text-[var(--muted-ink)]">
              Confirmed practice orders will appear here.
            </p>
          </div>
        </div>
      ) : (
        <>
          <table className="hidden w-full table-fixed border-collapse text-left text-sm md:table [&_td]:px-2 [&_td]:py-4 [&_th]:px-2 [&_th]:py-3">
            <caption className="sr-only">Paper trading fill activity</caption>
            <thead>
              <tr className="border-b border-[var(--ledger-rule)] text-xs tracking-[0.04em] text-[var(--muted-ink)]">
                <th scope="col">Side</th>
                <th scope="col">Instrument</th>
                <th scope="col">Quantity</th>
                <th scope="col">Fill price</th>
                <th scope="col">Charges</th>
                <th scope="col">Cash effect</th>
                <th scope="col">Realized P&amp;L</th>
                <th scope="col">Filled at</th>
              </tr>
            </thead>
            <tbody>
              {fills.map((fill) => (
                <tr key={fill.draftId} className="border-b border-[var(--soft-rule)] align-top">
                  <td className="font-semibold capitalize">{fill.side}</td>
                  <td>
                    <span className="block font-semibold">{fill.tradingSymbol}</span>
                    <span className="font-data text-xs text-[var(--muted-ink)]">
                      {fill.exchange}
                    </span>
                  </td>
                  <td className="font-data tabular-nums">{fill.quantity}</td>
                  <td className="font-data tabular-nums">
                    {formatPaperCurrency(fill.fillPricePaise)}
                  </td>
                  <td className="font-data tabular-nums">
                    {formatPaperCurrency(fill.chargesPaise)}
                  </td>
                  <td className="font-data tabular-nums">
                    {formatSignedPaperCurrency(fill.cashEffectPaise)}
                  </td>
                  <td
                    className={`font-data tabular-nums ${
                      fill.realizedPnlPaise < 0 ? 'text-[var(--risk-brick)]' : ''
                    }`}
                  >
                    {formatSignedPaperCurrency(fill.realizedPnlPaise)}
                  </td>
                  <td className="font-data text-xs">{fillDate(fill.filledAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="divide-y divide-[var(--soft-rule)] border-x border-b border-[var(--ledger-rule)] md:hidden">
            {fills.map((fill) => (
              <article
                key={fill.draftId}
                className="bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,var(--soft-rule)_32px)] px-[18px] py-5"
                aria-label={`${fill.side} ${fill.tradingSymbol} fill`}
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-display font-semibold">{fill.tradingSymbol}</h3>
                  <span className="font-semibold capitalize">{fill.side}</span>
                </div>
                <dl className="mt-4 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-3 text-sm">
                  <dt>Quantity</dt>
                  <dd className="font-data text-right tabular-nums">{fill.quantity}</dd>
                  <dt>Fill price</dt>
                  <dd className="font-data text-right tabular-nums">
                    {formatPaperCurrency(fill.fillPricePaise)}
                  </dd>
                  <dt>Charges</dt>
                  <dd className="font-data text-right tabular-nums">
                    {formatPaperCurrency(fill.chargesPaise)}
                  </dd>
                  <dt>Cash effect</dt>
                  <dd className="font-data text-right tabular-nums">
                    {formatSignedPaperCurrency(fill.cashEffectPaise)}
                  </dd>
                  <dt>Realized P&amp;L</dt>
                  <dd
                    className={`font-data text-right tabular-nums ${
                      fill.realizedPnlPaise < 0 ? 'text-[var(--risk-brick)]' : ''
                    }`}
                  >
                    {formatSignedPaperCurrency(fill.realizedPnlPaise)}
                  </dd>
                  <dt>Filled at</dt>
                  <dd className="font-data max-w-44 text-right text-xs">
                    {fillDate(fill.filledAt)}
                  </dd>
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
