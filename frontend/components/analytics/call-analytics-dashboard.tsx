'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, CheckCircle2, CircleX, RefreshCw, ShieldCheck } from 'lucide-react';
import { Reveal } from '@/components/app/reveal';
import { useAnimatedNumber } from '@/hooks/use-animated-number';
import {
  type CallAnalyticsSummary,
  type CallDetail,
  decodeCallAnalyticsSummary,
} from '@/lib/call-analytics';
import { cn } from '@/lib/shadcn/utils';

const DETAIL_LABELS: Record<CallDetail, string> = {
  grounded_answer_delivered: 'Grounded answer delivered',
  market_quote_delivered: 'Trusted quote delivered',
  historical_return_calculated: 'Historical return calculated',
  paper_fill_completed: 'Paper fill completed',
  human_help_created: 'Human help created',
  no_completed_action: 'No verified action completed',
  incomplete: 'Call ended incomplete',
  no_response: 'No response',
  tool_unavailable: 'Required tool unavailable',
  system_error: 'System error',
};

function MetricCard({
  label,
  value,
  tone,
  suffix = '',
}: {
  label: string;
  value: number;
  tone: 'blue' | 'green' | 'red' | 'ink';
  suffix?: string;
}) {
  const animated = useAnimatedNumber(value, { duration: 420, from: 0 });
  return (
    <article
      className={cn(
        'rounded-[12px] border bg-[var(--surface)] p-5 sm:p-6',
        tone === 'blue' && 'border-[var(--ledger-blue)]',
        tone === 'green' && 'border-[var(--banknote-green)]',
        tone === 'red' && 'border-[var(--risk-brick)]',
        tone === 'ink' && 'border-[var(--ledger-rule)]'
      )}
    >
      <p className="font-data text-[11px] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
        {label}
      </p>
      <p className="font-display mt-4 text-4xl font-bold tracking-[-0.04em] tabular-nums sm:text-5xl">
        <span aria-hidden="true">
          {Math.round(animated)}
          {suffix}
        </span>
        <span className="sr-only">
          {value}
          {suffix}
        </span>
      </p>
    </article>
  );
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

export function CallAnalyticsDashboard() {
  const [summary, setSummary] = useState<CallAnalyticsSummary | null>(null);
  const [status, setStatus] = useState<'loading' | 'live' | 'unavailable'>('loading');

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/analytics', { cache: 'no-store' });
      if (!response.ok) throw new Error('Analytics request failed');
      setSummary(decodeCallAnalyticsSummary(await response.json()));
      setStatus('live');
    } catch {
      setStatus('unavailable');
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const totals = summary?.totals ?? {
    total_calls: 0,
    successful_calls: 0,
    failed_calls: 0,
    success_rate_percent: 0,
  };

  return (
    <main className="hero-paper-pattern min-h-svh pb-16">
      <header className="border-b border-[var(--ledger-rule)] bg-[rgb(246_242_232/0.92)] backdrop-blur-md">
        <div className="section-shell flex min-h-18 items-center justify-between gap-4">
          <a href="/" className="flex items-center gap-3 font-semibold text-[var(--ledger-ink)]">
            <ArrowLeft aria-hidden="true" className="size-4" />
            Back to FinEd Saathi
          </a>
          <div
            className="flex items-center gap-2 text-sm text-[var(--muted-ink)]"
            aria-live="polite"
          >
            <span
              className={cn(
                'size-2 rounded-full',
                status === 'live' ? 'bg-[var(--banknote-green)]' : 'bg-[var(--risk-brick)]'
              )}
            />
            {status === 'loading'
              ? 'Loading real call data'
              : status === 'live'
                ? 'Live call data'
                : 'Data temporarily unavailable'}
          </div>
        </div>
      </header>

      <section className="section-shell pt-10 sm:pt-14">
        <Reveal>
          <div className="grid gap-6 border-b border-[var(--ledger-rule)] pb-8 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
            <div>
              <p className="font-data text-xs tracking-[0.1em] text-[var(--ledger-blue)] uppercase">
                Day 8 · Call analytics
              </p>
              <h1 className="font-display balance-text mt-3 max-w-3xl text-4xl font-bold tracking-[-0.045em] sm:text-6xl">
                Every ended session becomes one honest outcome.
              </h1>
            </div>
            <button
              type="button"
              onClick={() => void refresh()}
              className="flex min-h-11 items-center justify-center gap-2 rounded-[10px] border border-[var(--ledger-blue)] bg-[var(--surface)] px-4 font-semibold text-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] lg:justify-self-end"
            >
              <RefreshCw aria-hidden="true" className="size-4" />
              Refresh now
            </button>
          </div>
        </Reveal>

        <Reveal delay={0.05} className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Total calls" value={totals.total_calls} tone="blue" />
          <MetricCard label="Successful calls" value={totals.successful_calls} tone="green" />
          <MetricCard label="Failed calls" value={totals.failed_calls} tone="red" />
          <MetricCard
            label="Success rate"
            value={totals.success_rate_percent}
            suffix="%"
            tone="ink"
          />
        </Reveal>

        <div className="mt-7 grid gap-5 lg:grid-cols-[0.72fr_1.28fr]">
          <Reveal delay={0.1}>
            <aside className="rounded-[12px] border border-[var(--banknote-green)] bg-[var(--green-wash)] p-6">
              <div className="flex items-center gap-3">
                <CheckCircle2 aria-hidden="true" className="size-5 text-[var(--banknote-green)]" />
                <h2 className="font-display text-xl font-bold">What success means</h2>
              </div>
              <p className="mt-4 leading-7 text-[var(--ledger-ink)]">
                {summary?.success_definition ?? 'Waiting for the real analytics snapshot.'}
              </p>
              <div className="mt-6 border-t border-[rgb(31_107_79/0.25)] pt-5">
                <p className="flex gap-2 text-sm leading-6 text-[var(--muted-ink)]">
                  <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                  No phone numbers, participant identities or transcripts are collected for this
                  dashboard.
                </p>
              </div>
            </aside>
          </Reveal>

          <Reveal delay={0.15}>
            <section className="overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)]">
              <div className="flex items-center justify-between gap-3 border-b border-[var(--soft-rule)] p-5 sm:p-6">
                <div>
                  <p className="font-data text-[11px] tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
                    Anonymous ledger
                  </p>
                  <h2 className="font-display mt-1 text-2xl font-bold">Recent calls</h2>
                </div>
                <span className="font-data text-xs text-[var(--muted-ink)]">Auto-refresh 5s</span>
              </div>
              {!summary?.recent_calls.length ? (
                <div className="grid min-h-64 place-items-center p-8 text-center">
                  <div>
                    <CircleX
                      aria-hidden="true"
                      className="mx-auto size-7 text-[var(--muted-ink)]"
                    />
                    <p className="font-display mt-3 text-lg font-semibold">No ended calls yet</p>
                    <p className="mt-1 text-sm text-[var(--muted-ink)]">
                      End a real browser or SIP session to create the first row.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[42rem] border-collapse text-left">
                    <thead className="bg-[var(--paper)] text-xs text-[var(--muted-ink)] uppercase">
                      <tr>
                        <th className="px-5 py-3 font-semibold">Call</th>
                        <th className="px-5 py-3 font-semibold">Channel</th>
                        <th className="px-5 py-3 font-semibold">Duration</th>
                        <th className="px-5 py-3 font-semibold">Outcome</th>
                        <th className="px-5 py-3 font-semibold">Completed detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.recent_calls.map((call) => (
                        <tr key={call.call_id} className="border-t border-[var(--soft-rule)]">
                          <td className="px-5 py-4">
                            <code className="font-data text-xs">{call.call_id.slice(0, 14)}…</code>
                            <span className="mt-1 block text-xs text-[var(--muted-ink)]">
                              {new Intl.DateTimeFormat('en-IN', {
                                dateStyle: 'medium',
                                timeStyle: 'short',
                              }).format(new Date(call.started_at))}
                            </span>
                          </td>
                          <td className="px-5 py-4 capitalize">{call.channel}</td>
                          <td className="font-data px-5 py-4 text-sm">
                            {formatDuration(call.duration_seconds)}
                          </td>
                          <td className="px-5 py-4">
                            <span
                              className={cn(
                                'rounded-[8px] px-2.5 py-1 text-xs font-semibold capitalize',
                                call.outcome === 'successful'
                                  ? 'bg-[var(--green-wash)] text-[var(--banknote-green)]'
                                  : 'bg-[var(--risk-wash)] text-[var(--risk-brick)]'
                              )}
                            >
                              {call.outcome}
                            </span>
                          </td>
                          <td className="px-5 py-4 text-sm">{DETAIL_LABELS[call.detail]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </Reveal>
        </div>
      </section>
    </main>
  );
}
