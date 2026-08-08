'use client';

import Image from 'next/image';
import { ArrowRight, ChevronDown, ExternalLink, Mic, ShieldCheck } from 'lucide-react';
import { HeroMarketLedger } from '@/components/app/hero-market-ledger';
import { ModeBento } from '@/components/app/mode-bento';
import { Reveal } from '@/components/app/reveal';
import { SiteNav } from '@/components/app/site-nav';
import { Button } from '@/components/ui/button';
import type { LearningMode } from '@/lib/learning-modes';

const educationBoundary =
  'Education only. FinEd explains concepts and paper practice; it does not recommend or execute trades. Personalised decisions belong with a SEBI-registered investment adviser.';

const steps = [
  {
    number: '01',
    title: 'Choose a learning topic',
    body: 'Pick stocks, SIPs, ETFs, gold, F&O, IPOs, bonds or an open market question.',
  },
  {
    number: '02',
    title: 'Ask naturally',
    body: 'Speak in English, Hindi, or both. FinEd matches the language style you use.',
  },
  {
    number: '03',
    title: 'Check the explanation',
    body: 'Hear the concept, inspect the math when it applies, and open the named dated source.',
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

const safetyFacts = [
  ['Paper trading only', 'Virtual orders use practice cash and never become real trades.'],
  ['No recommendations', 'Learn concepts and risk without a buy call, target or allocation.'],
  ['F&O simulation only', 'Understand mechanics and substantial-loss risk in a protected mode.'],
  ['Dated evidence', 'Rules and fees are paired with their publisher and last-checked date.'],
] as const;

const faqs = [
  {
    question: 'Will FinEd recommend a stock?',
    answer:
      'No. FinEd explains products, charges, taxes and risks. It does not recommend a security, target, strategy or allocation.',
  },
  {
    question: 'Is paper practice the same as real trading?',
    answer:
      'No. The workspace uses virtual cash and simulated fills for learning. Nothing in paper practice is a real order or a promise of real-world results.',
  },
  {
    question: 'How does FinEd explain fees and taxes?',
    answer:
      'It can use the delivery-only calculator for a schedule-backed illustration, then show the assumptions and sources. Actual charges depend on product, date and account records.',
  },
  {
    question: 'What is the basic difference between an ETF and a mutual fund?',
    answer:
      'An ETF trades on an exchange during market hours. A mutual fund unit is bought or redeemed with the fund at its applicable NAV. Their costs and liquidity mechanics can differ.',
  },
  {
    question: 'How often are sources updated?',
    answer:
      'The corpus is curated and versioned. Fee and rule explanations show the publisher, applicability date and last-verified date so you can judge whether a source fits your question.',
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

      <section className="hero-paper-pattern relative overflow-hidden pt-4 pb-14 sm:pt-8 sm:pb-16 lg:pt-10 lg:pb-20">
        <div className="section-shell grid items-start gap-10 lg:grid-cols-12 lg:items-center lg:gap-8">
          <Reveal data-gsap-reveal className="lg:col-span-7">
            <p className="font-data text-xs font-medium tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
              VOICE-FIRST FINANCIAL LITERACY FOR INDIA
            </p>
            <h1 className="font-display balance-text mt-5 max-w-[13ch] text-[clamp(2.5rem,7vw,5rem)] leading-[0.98] font-bold tracking-[-0.045em] text-[var(--ledger-ink)]">
              Learn the market before risking money.
            </h1>
            <p className="mt-6 max-w-[58ch] text-[clamp(1.05rem,2vw,1.25rem)] leading-[1.55] text-[var(--muted-ink)]">
              FinEd Saathi explains Indian market concepts, charges and risks in English, Hindi, or
              both. Speak with Nikhil, learn from dated sources, then rehearse decisions with
              virtual cash.
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
                <a href="#paper-practice">
                  Explore paper trading
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
                  Connection failed. Your learning mode is saved and no paper order was placed.
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

            <div className="mt-6 flex max-w-[64ch] flex-wrap gap-x-5 gap-y-2 border-t border-[var(--ledger-rule)] pt-4 text-sm leading-6 text-[var(--muted-ink)]">
              <span>Paper trading only</span>
              <span>Official sources, shown with dates</span>
              <span>{educationBoundary}</span>
            </div>
          </Reveal>

          <div className="lg:col-span-5">
            <HeroMarketLedger />
          </div>
        </div>
      </section>

      <section
        id="topics"
        className="section-space scroll-mt-20 border-t border-[var(--ledger-rule)]"
      >
        <Reveal data-gsap-reveal className="section-shell">
          <SectionHeading
            eyebrow="Choose before you connect"
            title="What do you want to understand today?"
            copy="Choose one of eight modes to give your voice session a clear learning focus. You can choose a different mode before your next call."
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
        className="section-space scroll-mt-20 border-t border-[var(--ledger-rule)] bg-[var(--surface)]"
      >
        <Reveal data-gsap-reveal className="section-shell">
          <SectionHeading eyebrow="Three clear steps" title="How it works" />
          <ol className="mt-10 grid gap-px overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--ledger-rule)] md:grid-cols-3">
            {steps.map((step, index) => (
              <li
                key={step.number}
                data-gsap-reveal
                className="bg-[var(--surface)] p-[18px] sm:p-6"
              >
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

      <section
        id="paper-practice"
        className="section-space scroll-mt-20 border-t border-[var(--ledger-rule)]"
      >
        <Reveal data-gsap-reveal className="section-shell">
          <div className="grid gap-8 lg:grid-cols-12 lg:items-center">
            <div className="lg:col-span-5">
              <SectionHeading
                eyebrow="Safe paper practice"
                title="Practise with ₹1,00,000 virtual cash"
                copy="Learn how an order review, simulated fill and portfolio ledger fit together. Paper practice stays in your browser and uses no real money."
              />
              <div className="mt-7 rounded-[12px] border border-[var(--banknote-green)] bg-[var(--green-wash)] p-[18px] text-[var(--banknote-green)]">
                <p className="font-display font-semibold">Paper trading only</p>
                <p className="mt-2 text-sm leading-6">
                  A trusted current quote is required before a simulated order can be reviewed.
                  Practice results are not forecasts.
                </p>
              </div>
            </div>
            <figure className="overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-2 sm:p-3 lg:col-span-7">
              <Image
                src="/images/paper-practice-empty-v1.png"
                width={1536}
                height={1024}
                sizes="(min-width: 1024px) 650px, calc(100vw - 48px)"
                alt="Empty paper-practice portfolio with virtual cash and no simulated positions"
                className="h-auto w-full rounded-[8px]"
              />
              <figcaption className="px-2 pt-3 pb-1 text-sm leading-6 text-[var(--muted-ink)]">
                A calm starting state for learning order mechanics before any simulated position.
              </figcaption>
            </figure>
          </div>
        </Reveal>
      </section>

      <section
        id="sources"
        className="section-space scroll-mt-20 border-t border-[var(--ledger-rule)] bg-[var(--surface)]"
      >
        <Reveal data-gsap-reveal className="section-shell">
          <SectionHeading
            eyebrow="Official sources, shown with dates"
            title="A broker answer is not the only final authority."
            copy="FinEd keeps source classes separate and follows the higher-authority current source when records conflict. Each result exposes its publisher, date and link."
          />
          <p className="font-data mt-6 text-sm text-[var(--muted-ink)]">
            regulator &gt; exchange &gt; broker pricing &gt; broker support &gt; broker education
          </p>
          <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-12">
            {sourceCards.map((source, index) => (
              <article
                key={source.title}
                data-gsap-reveal
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
                  className="mt-5 inline-flex min-h-11 items-center gap-2 font-semibold text-[var(--ledger-blue)] underline decoration-[var(--ledger-rule)] underline-offset-4 hover:text-[var(--ledger-blue-hover)]"
                >
                  Open source <ExternalLink aria-hidden="true" className="size-4" />
                </a>
              </article>
            ))}
          </div>
        </Reveal>
      </section>

      <section
        id="safety"
        className="section-space scroll-mt-20 border-t border-[var(--ledger-rule)]"
      >
        <Reveal data-gsap-reveal className="section-shell">
          <SectionHeading
            eyebrow="Safety and beginner questions"
            title="Built to explain, not persuade."
            copy="The learning boundary stays visible before a call, during paper practice and beside higher-risk topics."
          />
          <div className="mt-10 grid gap-px overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--ledger-rule)] sm:grid-cols-2 lg:grid-cols-4">
            {safetyFacts.map(([title, body], index) => (
              <article
                key={title}
                data-gsap-reveal
                className="min-h-44 bg-[var(--surface)] p-[18px] sm:p-6"
              >
                <span className="font-data text-sm font-medium text-[var(--ledger-blue)]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="font-display mt-7 text-lg font-semibold">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--muted-ink)]">{body}</p>
              </article>
            ))}
          </div>

          <div className="mt-14 grid gap-10 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <p className="font-data text-xs font-medium tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
                FAQ
              </p>
              <h2 className="font-display balance-text mt-4 text-[clamp(2rem,4vw,3.5rem)] leading-[1.04] font-bold tracking-[-0.035em]">
                Questions worth asking first
              </h2>
            </div>
            <div className="grid gap-3 lg:col-span-8">
              {faqs.map((faq) => (
                <details
                  key={faq.question}
                  className="group rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] open:border-[var(--ledger-blue)]"
                >
                  <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 rounded-[12px] px-[18px] py-4 font-semibold transition-colors duration-200 ease-out hover:bg-[var(--blue-wash)] sm:px-6 [&::-webkit-details-marker]:hidden">
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
          </div>
        </Reveal>
      </section>

      <section className="border-y border-[var(--ledger-rule)] bg-[var(--blue-wash)] py-16 sm:py-20">
        <Reveal
          data-gsap-reveal
          className="section-shell flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-end"
        >
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
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#CBD3DE]">{educationBoundary}</p>
            <p className="mt-3 text-sm text-[#CBD3DE]">
              India voice: Nikhil, Conversational, powered by Murf Falcon 2.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <a
              href="#sources"
              className="flex min-h-11 items-center text-[#D8E5FA] underline underline-offset-4"
            >
              Source methodology
            </a>
            <a
              href="https://github.com/himanshu748/fin-ed"
              target="_blank"
              rel="noreferrer"
              className="flex min-h-11 items-center text-[#D8E5FA] underline underline-offset-4"
            >
              Public repository
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
