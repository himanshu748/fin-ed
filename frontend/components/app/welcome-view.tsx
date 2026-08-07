'use client';

import { ArrowRight, ChevronDown, ExternalLink, Mic, ShieldCheck } from 'lucide-react';
import { FeeReceipt } from '@/components/app/fee-receipt';
import { ModeBento } from '@/components/app/mode-bento';
import { Reveal } from '@/components/app/reveal';
import { SiteNav } from '@/components/app/site-nav';
import { Button } from '@/components/ui/button';
import sixRupeeFixture from '@/data/six-rupee-delivery.json';
import type { LearningMode } from '@/lib/learning-modes';

const educationBoundary =
  'Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP. Personalised decisions belong with a SEBI-registered investment adviser.';
const reconciliationLocation = 'contract-note total charges, ledger or available funds, or P&L';
const contractNotePriority =
  'Contract-note or Trades & Charges rows outrank this generic estimate.';
const {
  assumptions: sixRupeeAssumptions,
  result: sixRupeeResult,
  rules: sixRupeeRules,
} = sixRupeeFixture;

const steps = [
  {
    number: '01',
    title: 'Choose a topic',
    body: 'Stocks, SIPs, ETFs, gold, F&O, IPOs, bonds or an open Indian market question.',
  },
  {
    number: '02',
    title: 'Ask naturally',
    body: 'Speak in English, Hindi, or both. FinEd matches the language style you use.',
  },
  {
    number: '03',
    title: 'Check the explanation',
    body: 'Hear the answer, inspect the math and open the named source with its verification date.',
  },
] as const;

const sourceCards = [
  {
    rank: '01A',
    type: 'Regulator and government',
    publisher: 'SEBI',
    title: 'SEBI Stock Brokers Regulations, Schedule V',
    applicability: 'Official cash-market turnover fee authority',
    verified: 'Verified 06 Aug 2026',
    href: 'https://www.sebi.gov.in/sebi_data/commondocs/stockbroamendregu_p.pdf',
  },
  {
    rank: '01B',
    type: 'Regulator and government',
    publisher: 'SEBI',
    title: 'SEBI FAQ on Indian Stamp Act amendments',
    applicability: 'Stamp-duty rules effective 01 Jul 2020',
    verified: 'Verified 06 Aug 2026',
    href: 'https://www.sebi.gov.in/sebi_data/faqfiles/sep-2020/1599820228476.pdf',
  },
  {
    rank: '02',
    type: 'Exchange',
    publisher: 'NSE',
    title: 'Circular NSE/FA/73061',
    applicability: 'Applicable 01 Mar 2026',
    verified: 'Verified 06 Aug 2026',
    href: 'https://nsearchives.nseindia.com/content/circulars/FA73061.pdf',
  },
  {
    rank: '03',
    type: 'Broker pricing and support',
    publisher: 'Angel One',
    title: 'Brokerage charges',
    applicability: 'Baseline effective 01 Nov 2024',
    verified: 'Verified 06 Aug 2026',
    href: 'https://www.angelone.in/support/charges-and-cashbacks/brokerage-charges',
  },
  {
    rank: '04',
    type: 'Broker education',
    publisher: 'Angel One',
    title: 'ETF complete guide',
    applicability: 'Updated 05 May 2026',
    verified: 'Verified 06 Aug 2026',
    href: 'https://www.angelone.in/knowledge-center/online-share-trading/etf',
  },
] as const;

const capabilities = [
  ['8 learning modes', 'Pick one context before each call.'],
  ['Nikhil, Conversational', 'Indian English and Hindi voice using Murf Falcon 2.'],
  ['Angel One baseline', 'The first broker schedule used for fee illustrations.'],
  ['Deterministic calculator', 'Delivery-cost math is computed, not guessed by the model.'],
  ['No recommendations', 'Concepts and risk education, never a buy or sell call.'],
  ['No trade execution', 'FinEd cannot place, modify or cancel an order.'],
  ['No broker credentials', 'It never needs your password, PIN or OTP.'],
  ['F&O simulation only', 'Mechanics and risk in a protected learning mode.'],
] as const;

const faqs = [
  {
    question: 'Will FinEd recommend a stock?',
    answer:
      'No. FinEd explains concepts, charges, taxes and risks. It does not recommend a security, target, strategy or allocation.',
  },
  {
    question: 'Why can ₹50 differ from the current estimate?',
    answer: `The remembered ₹50 is unresolved. This illustration uses ${sixRupeeAssumptions.executed_buy_orders} executed buy order, ${sixRupeeAssumptions.executed_sell_orders} executed sell order and ${sixRupeeAssumptions.demat_debits} sell-side DP debit. Brokerage is ${sixRupeeRules.brokerage}; buy brokerage is ₹${sixRupeeResult.brokerage_buy}, sell brokerage is ₹${sixRupeeResult.brokerage_sell}, DP is ₹${sixRupeeResult.dp_charge_before_gst} before GST, total charges are ₹${sixRupeeResult.total_charges}, the ratio is ${sixRupeeResult.fee_to_investment_percent}% and break-even is ₹${sixRupeeResult.break_even_sell_price}. First locate where ₹50 appeared in ${reconciliationLocation}. Then check the trade date, delivery versus intraday, executed order counts, sell-side DP debit count, promotion status, and separate account or service charges. ${contractNotePriority}`,
  },
  {
    question: 'What is the basic difference between an ETF and a mutual fund?',
    answer:
      'An ETF trades on an exchange during market hours, so you generally need a demat and trading account. A mutual fund unit is bought or redeemed with the fund at its applicable NAV. Costs and liquidity mechanics also differ.',
  },
  {
    question: 'Does FinEd access my Angel One account?',
    answer:
      'No. Angel One is a pricing and education baseline only. FinEd does not sign in to your account and never asks for a password, PIN or OTP.',
  },
  {
    question: 'How often are sources updated?',
    answer:
      'The corpus is curated and versioned. Every fee or rule answer should show its publisher, applicability date and last-verified date so you can check whether it fits your trade date.',
  },
] as const;

function SectionHeading({
  eyebrow,
  title,
  copy,
}: {
  eyebrow: string;
  title: string;
  copy?: string;
}) {
  return (
    <div className="max-w-3xl">
      <p className="font-data text-xs font-medium tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
        {eyebrow}
      </p>
      <h2 className="font-display balance-text mt-4 text-[clamp(2rem,4vw,3.5rem)] leading-[1.04] font-bold tracking-[-0.035em] text-[var(--ledger-ink)]">
        {title}
      </h2>
      {copy && (
        <p className="mt-5 max-w-[68ch] text-lg leading-8 text-[var(--muted-ink)]">{copy}</p>
      )}
    </div>
  );
}

function StepSketch({ index }: { index: number }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 88 56"
      className="h-14 w-[5.5rem] text-[var(--ledger-blue)]"
      fill="none"
    >
      {index === 0 && (
        <>
          <rect x="5" y="8" width="78" height="40" rx="8" stroke="currentColor" strokeWidth="1.7" />
          <path
            d="M18 20H70M18 28H60M18 36H52"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
          <circle cx="73" cy="36" r="5" fill="#EAF1FD" stroke="currentColor" strokeWidth="1.7" />
        </>
      )}
      {index === 1 && (
        <>
          <path
            d="M12 20V36M21 12V44M30 18V38M39 8V48M48 16V40M57 11V45M66 20V36M75 24V32"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path d="M9 50H78" stroke="#D8D0C0" strokeWidth="1.5" />
        </>
      )}
      {index === 2 && (
        <>
          <path d="M7 8H61V48H7V8Z" stroke="currentColor" strokeWidth="1.7" />
          <path
            d="M16 18H51M16 26H47M16 34H42"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
          <path d="M61 19H80V43H52V36" stroke="#1F6B4F" strokeWidth="1.7" />
          <path
            d="M60 34L65 39L74 27"
            stroke="#1F6B4F"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
    </svg>
  );
}

interface WelcomeViewProps {
  learningMode: LearningMode;
  onLearningModeChange: (mode: LearningMode) => void;
  onStartCall: () => void;
  isConnecting: boolean;
  connectionError: boolean;
}

export function WelcomeView({
  learningMode,
  onLearningModeChange,
  onStartCall,
  isConnecting,
  connectionError,
}: WelcomeViewProps) {
  const connectLabel = isConnecting ? 'Connecting to FinEd Saathi' : 'Talk to FinEd Saathi';

  return (
    <div id="top" className="min-h-svh bg-[var(--paper)]">
      <SiteNav connectLabel={connectLabel} isConnecting={isConnecting} onConnect={onStartCall} />

      <section className="hero-paper-pattern relative flex min-h-[calc(100svh-4.5rem)] items-start overflow-hidden pt-4 pb-12 sm:pt-8 sm:pb-16 lg:pt-10 lg:pb-20">
        <div className="section-shell grid items-center gap-12 lg:grid-cols-12 lg:gap-8">
          <div className="lg:col-span-7">
            <p className="font-data text-xs font-medium tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
              VOICE-FIRST FINANCIAL LITERACY FOR INDIA
            </p>
            <h1 className="font-display balance-text mt-5 max-w-[13ch] text-[clamp(2.5rem,7vw,5rem)] leading-[0.98] font-bold tracking-[-0.045em] text-[var(--ledger-ink)]">
              Same price. Why did I still lose money?
            </h1>
            <p className="mt-6 max-w-[58ch] text-[clamp(1.05rem,2vw,1.25rem)] leading-[1.55] text-[var(--muted-ink)]">
              FinEd Saathi explains Indian market concepts, charges and risks in English, Hindi, or
              both. Ask by voice, see the math, and verify the source. It provides education, not
              investment advice.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Button
                type="button"
                size="lg"
                disabled={isConnecting}
                onClick={onStartCall}
                className="min-w-60"
              >
                <Mic aria-hidden="true" />
                {connectLabel}
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#why-the-loss">
                  See the ₹6 breakdown
                  <ArrowRight aria-hidden="true" />
                </a>
              </Button>
            </div>

            {connectionError && (
              <div
                role="alert"
                className="mt-5 max-w-2xl rounded-[12px] border border-[var(--risk-brick)] bg-[var(--risk-wash)] p-[18px] text-[var(--risk-brick)]"
              >
                <p className="leading-6">
                  Connection failed. Your broker account and credentials were not accessed.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onStartCall}
                  className="mt-3 border-[var(--risk-brick)] bg-[var(--surface)] text-[var(--risk-brick)]"
                >
                  Try connecting again
                </Button>
              </div>
            )}

            <p className="mt-6 max-w-[62ch] text-sm leading-6 text-[var(--muted-ink)]">
              {educationBoundary}
            </p>
          </div>

          <div className="lg:col-span-5">
            <FeeReceipt />
          </div>
        </div>
      </section>

      <section id="topics" className="section-space border-t border-[var(--ledger-rule)]">
        <Reveal className="section-shell">
          <SectionHeading
            eyebrow="Choose before you connect"
            title="What do you want to understand today?"
            copy="Your selected mode travels with the voice session and keeps the explanation focused. You can choose a new mode before the next call."
          />
          <div className="mt-10">
            <ModeBento
              value={learningMode}
              onChange={onLearningModeChange}
              disabled={isConnecting}
              disabledReason="Mode selection is paused while connecting."
            />
          </div>
        </Reveal>
      </section>

      <section
        id="how-it-works"
        className="section-space border-t border-[var(--ledger-rule)] bg-[var(--surface)]"
      >
        <Reveal className="section-shell">
          <SectionHeading eyebrow="Three clear steps" title="How it works" />
          <ol className="mt-10 grid gap-px overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--ledger-rule)] md:grid-cols-3">
            {steps.map((step, index) => (
              <li key={step.number} className="bg-[var(--surface)] p-[18px] sm:p-6">
                <div className="flex items-start justify-between gap-4">
                  <span className="font-data text-sm font-medium text-[var(--ledger-blue)]">
                    {step.number}
                  </span>
                  <StepSketch index={index} />
                </div>
                <h3 className="font-display mt-8 text-xl font-semibold">{step.title}</h3>
                <p className="mt-3 leading-7 text-[var(--muted-ink)]">{step.body}</p>
              </li>
            ))}
          </ol>
        </Reveal>
      </section>

      <section id="why-the-loss" className="section-space border-t border-[var(--ledger-rule)]">
        <Reveal className="section-shell">
          <SectionHeading
            eyebrow="Current delivery illustration"
            title="The price loss was zero. The transaction cost was not."
            copy="This one-share NSE example uses the current versioned Angel One baseline. It separates the market result from the cost of completing the transaction."
          />
          <div className="mt-10 grid overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] lg:grid-cols-12">
            <div className="border-b border-[var(--ledger-rule)] p-[18px] sm:p-6 lg:col-span-5 lg:border-r lg:border-b-0">
              <FeeReceipt compact />
            </div>
            <div className="p-[18px] sm:p-6 lg:col-span-7">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--soft-rule)] pb-5">
                <div>
                  <p className="font-data text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                    Assumptions
                  </p>
                  <p className="mt-2 font-semibold">
                    NSE delivery · {sixRupeeAssumptions.quantity} share ·{' '}
                    {sixRupeeAssumptions.executed_buy_orders} executed buy order ·{' '}
                    {sixRupeeAssumptions.executed_sell_orders} executed sell order ·{' '}
                    {sixRupeeAssumptions.demat_debits} sell-side DP debit · standard post-promotion
                    brokerage
                  </p>
                </div>
                <span className="rounded-[8px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] px-3 py-2 text-sm font-semibold text-[var(--ledger-blue)]">
                  Illustrative estimate
                </span>
              </div>
              <div className="mt-5 grid gap-2 rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--paper)] p-4 text-sm leading-6 text-[var(--muted-ink)]">
                <p>
                  <strong className="text-[var(--ledger-ink)]">Brokerage formula:</strong>{' '}
                  {sixRupeeRules.brokerage}.
                </p>
                <p>
                  <strong className="text-[var(--ledger-ink)]">DP formula:</strong>{' '}
                  {sixRupeeRules.dp_charge}.
                </p>
              </div>
              <dl className="mt-2">
                {[
                  [
                    'Trade value and market P&L',
                    `₹${sixRupeeAssumptions.buy_price} buy · ₹${sixRupeeAssumptions.sell_price} sell · ₹0.00 P&L`,
                  ],
                  [
                    `Buy brokerage (${sixRupeeAssumptions.executed_buy_orders} executed order)`,
                    `₹${sixRupeeResult.brokerage_buy}`,
                  ],
                  [
                    `Sell brokerage (${sixRupeeAssumptions.executed_sell_orders} executed order)`,
                    `₹${sixRupeeResult.brokerage_sell}`,
                  ],
                  ['Statutory and exchange charges', 'about ₹0.01'],
                  ['GST, 18% of taxable charges', 'about ₹5.40'],
                  [
                    `DP charge (${sixRupeeAssumptions.demat_debits} sell-side demat debit, before GST)`,
                    `₹${sixRupeeResult.dp_charge_before_gst}`,
                  ],
                ].map(([label, amount]) => (
                  <div
                    key={label}
                    className="grid gap-1 border-b border-[var(--soft-rule)] py-4 sm:grid-cols-[1fr_auto] sm:items-center sm:gap-6"
                  >
                    <dt className="text-[var(--muted-ink)]">{label}</dt>
                    <dd className="font-data text-left font-medium text-[var(--ledger-ink)] sm:text-right">
                      {amount}
                    </dd>
                  </div>
                ))}
                <div className="grid gap-1 border-t-2 border-[var(--ledger-ink)] py-5 sm:grid-cols-[1fr_auto] sm:items-end sm:gap-6">
                  <dt>
                    <span className="font-display block text-xl font-bold">
                      Total charges and net result
                    </span>
                    <span className="mt-1 block text-sm text-[var(--muted-ink)]">
                      Fee-to-investment ratio {sixRupeeResult.fee_to_investment_percent}% of the ₹
                      {sixRupeeAssumptions.buy_price} buy value. Current illustrative break-even
                      sell price ₹{sixRupeeResult.break_even_sell_price}.
                    </span>
                  </dt>
                  <dd className="font-data text-left text-xl font-medium text-[var(--risk-brick)] sm:text-right">
                    about negative ₹{sixRupeeResult.total_charges}
                  </dd>
                </div>
              </dl>
              <div className="mt-5 rounded-[12px] border border-[var(--risk-brick)] bg-[var(--risk-wash)] p-4 text-sm leading-6 text-[var(--risk-brick)]">
                <p className="font-display font-semibold">₹50 status: unresolved</p>
                <p className="mt-2">
                  First locate whether ₹50 appeared in {reconciliationLocation}. Then confirm trade
                  date, delivery versus intraday, executed buy and sell order counts, sell-side DP
                  transaction or debit count, promotion status, and any separate account or service
                  charge.
                </p>
                <p className="mt-2 font-semibold">{contractNotePriority}</p>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      <section className="section-space border-t border-[var(--ledger-rule)] bg-[var(--ledger-ink)] text-[var(--surface)]">
        <Reveal className="section-shell grid gap-8 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-5">
            <p className="font-data text-xs tracking-[0.08em] text-[#AFC8F0] uppercase">
              Voice-session proof
            </p>
            <h2 className="font-display balance-text mt-4 text-[clamp(2rem,4vw,3.5rem)] leading-[1.04] font-bold tracking-[-0.035em]">
              It listens. Then it explains.
            </h2>
            <p className="mt-5 text-lg leading-8 text-[#CBD3DE]">
              The spoken answer stays concise. The visible transcript keeps the calculation and
              source links available for inspection.
            </p>
          </div>
          <div className="rounded-[12px] border border-[#41516A] bg-[#1B2C48] p-[18px] sm:p-6 lg:col-span-7">
            <div className="flex items-center gap-3 border-b border-[#41516A] pb-4">
              <span className="grid size-10 place-items-center rounded-[10px] bg-[#EAF1FD] text-[var(--ledger-blue)]">
                <Mic aria-hidden="true" className="size-5" />
              </span>
              <div>
                <p className="font-data text-xs tracking-[0.08em] text-[#AFC8F0] uppercase">
                  Example transcript
                </p>
                <p className="mt-1 text-sm text-[#CBD3DE]">Stocks mode</p>
              </div>
            </div>
            <blockquote className="mt-5 text-xl leading-8 font-semibold">
              “I bought and sold one share at ₹6. Why did I still lose ₹50?”
            </blockquote>
            <div className="mt-5 border-l-2 border-[#AFC8F0] pl-5 text-[0.98rem] leading-7 text-[#E6EAF0]">
              The price P&amp;L may be zero, but the remembered ₹50 is unresolved. First identify
              whether ₹50 appeared in {reconciliationLocation}. Then check one detail at a time:
              trade date, delivery versus intraday, executed buy and sell order counts, sell-side DP
              debit count, promotion status, and any separate account or service charge. The
              brokerage rule is {sixRupeeRules.brokerage}. This fixture has ₹
              {sixRupeeResult.brokerage_buy} buy brokerage, ₹{sixRupeeResult.brokerage_sell} sell
              brokerage and a ₹{sixRupeeResult.dp_charge_before_gst} sell-side DP debit before GST.
              It illustrates about ₹{sixRupeeResult.total_charges}, not the remembered ₹50.
            </div>
          </div>
        </Reveal>
      </section>

      <section id="sources" className="section-space border-t border-[var(--ledger-rule)]">
        <Reveal className="section-shell">
          <SectionHeading
            eyebrow="Curated and versioned sources"
            title="A broker answer is not the only final authority."
            copy="FinEd keeps source classes separate and follows the higher-authority current source when records conflict. Every answer should expose publisher, date and link."
          />
          <p className="font-data mt-6 text-sm text-[var(--muted-ink)]">
            regulator &gt; exchange &gt; broker pricing &gt; broker support &gt; broker education
          </p>
          <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-12">
            {sourceCards.map((source, index) => (
              <article
                key={source.title}
                className={`${index < 2 ? 'lg:col-span-7' : 'lg:col-span-5'} rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] transition-transform duration-200 ease-out hover:-translate-y-[3px] sm:p-6`}
              >
                <div className="flex items-start justify-between gap-4">
                  <span className="font-data text-sm font-medium text-[var(--ledger-blue)]">
                    {source.rank}
                  </span>
                  <ShieldCheck aria-hidden="true" className="size-6 text-[var(--banknote-green)]" />
                </div>
                <p className="font-data mt-7 text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                  {source.type}
                </p>
                <h3 className="font-display mt-2 text-xl font-semibold">
                  {source.publisher}: {source.title}
                </h3>
                <dl className="mt-4 grid gap-2 text-sm text-[var(--muted-ink)]">
                  <div className="flex flex-wrap justify-between gap-2">
                    <dt>Applicability</dt>
                    <dd className="font-data">{source.applicability}</dd>
                  </div>
                  <div className="flex flex-wrap justify-between gap-2">
                    <dt>Last checked</dt>
                    <dd className="font-data">{source.verified}</dd>
                  </div>
                </dl>
                <a
                  href={source.href}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-5 inline-flex min-h-10 items-center gap-2 font-semibold text-[var(--ledger-blue)] underline decoration-[var(--ledger-rule)] underline-offset-4 hover:text-[var(--ledger-blue-hover)]"
                >
                  Open source <ExternalLink aria-hidden="true" className="size-4" />
                </a>
              </article>
            ))}
          </div>
        </Reveal>
      </section>

      <section className="section-space border-t border-[var(--ledger-rule)] bg-[var(--surface)]">
        <Reveal className="section-shell">
          <SectionHeading
            eyebrow="Capabilities and boundaries"
            title="Built to explain, not persuade."
          />
          <div className="mt-10 grid gap-px overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--ledger-rule)] sm:grid-cols-2 lg:grid-cols-4">
            {capabilities.map(([title, body], index) => (
              <article key={title} className="min-h-48 bg-[var(--surface)] p-[18px] sm:p-6">
                <span className="font-data text-sm font-medium text-[var(--ledger-blue)]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="font-display mt-7 text-lg font-semibold">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--muted-ink)]">{body}</p>
              </article>
            ))}
          </div>
        </Reveal>
      </section>

      <section className="section-space border-t border-[var(--ledger-rule)]">
        <Reveal className="section-shell grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <SectionHeading
              eyebrow="Beginner questions"
              title="FAQ"
              copy="Short answers before you share any trade detail."
            />
          </div>
          <div className="grid gap-3 lg:col-span-8">
            {faqs.map((faq) => (
              <details
                key={faq.question}
                className="group rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] open:border-[var(--ledger-blue)]"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-[12px] px-[18px] py-4 font-semibold transition-colors duration-200 ease-out hover:bg-[var(--blue-wash)] sm:px-6 [&::-webkit-details-marker]:hidden">
                  {faq.question}
                  <ChevronDown
                    aria-hidden="true"
                    className="size-5 shrink-0 text-[var(--ledger-blue)] transition-transform duration-200 ease-out group-open:rotate-180"
                  />
                </summary>
                <p className="border-t border-[var(--soft-rule)] px-[18px] py-5 leading-7 text-[var(--muted-ink)] sm:px-6">
                  {faq.answer}
                </p>
              </details>
            ))}
          </div>
        </Reveal>
      </section>

      <section className="border-y border-[var(--ledger-rule)] bg-[var(--blue-wash)] py-16 sm:py-20">
        <Reveal className="section-shell flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-end">
          <div>
            <p className="font-data text-xs tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
              One concept at a time
            </p>
            <h2 className="font-display balance-text mt-4 max-w-[18ch] text-[clamp(2rem,4vw,3.5rem)] leading-[1.04] font-bold tracking-[-0.035em]">
              Learn the next concept, not the next trade.
            </h2>
          </div>
          <Button
            type="button"
            size="lg"
            disabled={isConnecting}
            onClick={onStartCall}
            className="min-w-60"
          >
            <Mic aria-hidden="true" />
            {connectLabel}
          </Button>
        </Reveal>
      </section>

      <footer className="bg-[var(--ledger-ink)] py-10 text-[var(--surface)]">
        <div className="section-shell grid gap-8 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="font-display text-xl font-bold">FinEd Saathi</p>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#CBD3DE]">
              Financial Services track. {educationBoundary}
            </p>
            <p className="mt-3 text-sm text-[#CBD3DE]">
              Indian voice: Nikhil, Conversational, powered by Murf Falcon 2.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <a
              href="#sources"
              className="flex min-h-10 items-center text-[#D8E5FA] underline underline-offset-4"
            >
              Source methodology
            </a>
            <a
              href="https://github.com/himanshu748/fin-ed"
              target="_blank"
              rel="noreferrer"
              className="flex min-h-10 items-center text-[#D8E5FA] underline underline-offset-4"
            >
              Public repository
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
