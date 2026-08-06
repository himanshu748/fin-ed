import sixRupeeFixture from '@/data/six-rupee-delivery.json';
import { cn } from '@/lib/shadcn/utils';

interface FeeReceiptProps {
  compact?: boolean;
  className?: string;
}

const { assumptions, result, rules } = sixRupeeFixture;

const receiptRows = [
  { label: 'Buy value', value: `₹${assumptions.buy_price}` },
  { label: 'Sell value', value: `₹${assumptions.sell_price}` },
  { label: 'Price P&L', value: '₹0.00' },
  { label: 'Illustrative charges', value: `about ₹${result.total_charges}` },
];

export function FeeReceipt({ compact = false, className }: FeeReceiptProps) {
  return (
    <figure className={cn('mx-auto w-full max-w-[32rem]', className)}>
      <div className="receipt-glow p-3 sm:p-7">
        <svg
          role="img"
          aria-labelledby="fee-receipt-title fee-receipt-description"
          className="h-auto w-full overflow-visible [filter:drop-shadow(0_18px_22px_rgb(21_35_59/0.09))]"
          viewBox="0 0 520 590"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <title id="fee-receipt-title">NSE delivery illustration</title>
          <desc id="fee-receipt-description">
            Buy ₹{assumptions.buy_price}, Sell ₹{assumptions.sell_price}, Price P&amp;L ₹0.00,
            Illustrative charges about ₹{result.total_charges}, Net about negative ₹
            {result.total_charges}.
          </desc>
          <path
            d="M34 18H486C497.046 18 506 26.9543 506 38V542L494 550L482 542L470 550L458 542L446 550L434 542L422 550L410 542L398 550L386 542L374 550L362 542L350 550L338 542L326 550L314 542L302 550L290 542L278 550L266 542L254 550L242 542L230 550L218 542L206 550L194 542L182 550L170 542L158 550L146 542L134 550L122 542L110 550L98 542L86 550L74 542L62 550L50 542L34 550C22.9543 550 14 541.046 14 530V38C14 26.9543 22.9543 18 34 18Z"
            fill="#FFFCF5"
            stroke="#D8D0C0"
            strokeWidth="2"
          />
          <path
            d="M42 106H478M42 176H478M42 246H478M42 316H478M42 386H478M42 472H478"
            stroke="#E9E3D7"
            strokeWidth="2"
          />
          <path d="M42 424H478" stroke="#D8D0C0" strokeWidth="3" />

          <text
            x="42"
            y="58"
            fill="#174EA6"
            fontFamily="var(--font-ibm-plex-mono), monospace"
            fontSize="14"
            fontWeight="500"
            letterSpacing="1.2"
          >
            NSE DELIVERY ILLUSTRATION
          </text>
          <text
            x="42"
            y="85"
            fill="#526174"
            fontFamily="var(--font-source-sans-3), sans-serif"
            fontSize="16"
          >
            One share · same buy and sell price
          </text>

          {receiptRows.map((row, index) => {
            const y = 149 + index * 70;

            return (
              <g key={row.label} aria-label={`${row.label} ${row.value}`}>
                <text
                  x="42"
                  y={y}
                  fill="#526174"
                  fontFamily="var(--font-source-sans-3), sans-serif"
                  fontSize="18"
                >
                  {row.label}
                </text>
                <text
                  x="478"
                  y={y}
                  textAnchor="end"
                  fill="#15233B"
                  fontFamily="var(--font-ibm-plex-mono), monospace"
                  fontSize="18"
                  fontWeight="500"
                >
                  {row.value}
                </text>
              </g>
            );
          })}

          <g aria-label={`Net about negative ₹${result.total_charges}`}>
            <text
              x="42"
              y="454"
              fill="#15233B"
              fontFamily="var(--font-manrope), sans-serif"
              fontSize="20"
              fontWeight="700"
            >
              Net result
            </text>
            <text
              x="478"
              y="454"
              textAnchor="end"
              fill="#A13D35"
              fontFamily="var(--font-ibm-plex-mono), monospace"
              fontSize="20"
              fontWeight="500"
            >
              negative ₹{result.total_charges}
            </text>
          </g>
          <text
            x="42"
            y="507"
            fill="#526174"
            fontFamily="var(--font-source-sans-3), sans-serif"
            fontSize="14"
          >
            Assumptions and effective schedule shown below
          </text>
          <text
            x="42"
            y="530"
            fill="#1F6B4F"
            fontFamily="var(--font-ibm-plex-mono), monospace"
            fontSize="13"
            fontWeight="500"
          >
            CURRENT ILLUSTRATION · NOT A TRADE QUOTE
          </text>
        </svg>
      </div>

      <div className="mt-3 grid gap-2 rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-4 text-sm leading-6 text-[var(--muted-ink)]">
        <p>
          <strong className="text-[var(--ledger-ink)]">Counted:</strong>{' '}
          {assumptions.executed_buy_orders} executed buy order, {assumptions.executed_sell_orders}{' '}
          executed sell order and {assumptions.demat_debits} sell-side DP debit.
        </p>
        <p>
          <strong className="text-[var(--ledger-ink)]">Brokerage rule:</strong> {rules.brokerage}.
          This fixture gives ₹{result.brokerage_buy} buy brokerage and ₹{result.brokerage_sell} sell
          brokerage.
        </p>
        <p>
          <strong className="text-[var(--ledger-ink)]">DP rule:</strong> {rules.dp_charge}. This
          fixture gives ₹{result.dp_charge_before_gst} before DP GST.
        </p>
      </div>

      {!compact && (
        <figcaption className="mx-auto mt-3 max-w-[44rem] text-sm leading-6 text-[var(--muted-ink)]">
          <strong className="text-[var(--risk-brick)]">₹50 status: unresolved.</strong> First locate
          whether it appeared in contract-note total charges, ledger or available funds, or P&amp;L.
          Then confirm trade date, delivery versus intraday, executed order counts, sell-side DP
          debit count, promotion status and separate account or service charges. Contract-note or
          Trades &amp; Charges rows outrank this generic estimate. ₹{result.total_charges} is a
          current illustration, not a reconstruction of the historical trade.
        </figcaption>
      )}
    </figure>
  );
}
