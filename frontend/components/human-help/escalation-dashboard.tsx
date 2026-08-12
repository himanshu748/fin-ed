'use client';

import { useHumanHelp } from '@/components/human-help/escalation-provider';

const REASON_LABELS = {
  suspected_fraud: 'Suspected fraud',
  decision_review: 'Human decision review',
} as const;

export function HumanHelpDashboard() {
  const humanHelp = useHumanHelp();
  const active = humanHelp.activeRequest;

  return (
    <main className="section-shell min-h-[calc(100svh-11rem)] py-5 lg:py-8">
      <section className="rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-[18px] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--soft-rule)] pb-5">
          <div>
            <p className="font-data text-xs tracking-[0.08em] text-[var(--ledger-blue)] uppercase">
              Human help
            </p>
            <h1 tabIndex={-1} className="font-display mt-2 text-3xl font-bold">
              Open request queue
            </h1>
            <p className="mt-2 max-w-2xl leading-7 text-[var(--muted-ink)]">
              Only the redacted summary approved by the learner appears here. Never add an OTP, PIN,
              password, PAN, Aadhaar or account number.
            </p>
          </div>
          <button
            type="button"
            onClick={humanHelp.close}
            className="min-h-11 rounded-[10px] border border-[var(--ledger-blue)] px-4 text-sm font-semibold text-[var(--ledger-blue)] hover:bg-[var(--blue-wash)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
          >
            Back
          </button>
        </div>

        {humanHelp.requests.length === 0 ? (
          <div className="grid min-h-72 place-items-center text-center">
            <div>
              <p className="font-display text-xl font-semibold">No open request in this session</p>
              <p className="mt-2 text-sm text-[var(--muted-ink)]">
                Normal learning questions should stay in the conversation.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(15rem,0.7fr)_minmax(0,1.3fr)]">
            <nav aria-label="Open human-help requests" className="space-y-2">
              {humanHelp.requests.map((request) => (
                <button
                  key={request.reference_id}
                  type="button"
                  aria-current={active?.reference_id === request.reference_id ? 'page' : undefined}
                  onClick={() => humanHelp.viewRequest(request.reference_id)}
                  className="w-full rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--paper)] p-4 text-left hover:border-[var(--ledger-blue)] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ledger-blue)]"
                >
                  <span className="font-data block text-[10px] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                    {request.status} · {request.urgency}
                  </span>
                  <code className="font-data mt-2 block text-xs break-all">
                    {request.reference_id}
                  </code>
                </button>
              ))}
            </nav>

            {active && (
              <article className="rounded-[12px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="rounded-[8px] bg-[var(--ledger-blue)] px-3 py-1.5 text-xs font-semibold text-white">
                    {REASON_LABELS[active.reason]}
                  </span>
                  <span className="font-data text-xs font-semibold uppercase">
                    {active.urgency} urgency
                  </span>
                </div>
                <h2 className="font-display mt-5 text-2xl font-bold">Request is open</h2>
                <dl className="mt-5 grid gap-5">
                  <div>
                    <dt className="font-data text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                      What happened
                    </dt>
                    <dd className="mt-2 leading-7">{active.summary}</dd>
                  </div>
                  <div>
                    <dt className="font-data text-xs tracking-[0.08em] text-[var(--muted-ink)] uppercase">
                      What FinEd checked
                    </dt>
                    <dd className="mt-2 leading-7">{active.checks_completed}</dd>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <div>
                      <dt className="font-data text-xs text-[var(--muted-ink)] uppercase">
                        Language
                      </dt>
                      <dd className="mt-1 capitalize">{active.language}</dd>
                    </div>
                    <div>
                      <dt className="font-data text-xs text-[var(--muted-ink)] uppercase">
                        Follow-up
                      </dt>
                      <dd className="mt-1">In this app</dd>
                    </div>
                    <div>
                      <dt className="font-data text-xs text-[var(--muted-ink)] uppercase">
                        Reference ID
                      </dt>
                      <dd className="font-data mt-1 text-xs break-all">{active.reference_id}</dd>
                    </div>
                  </div>
                </dl>
                <p className="mt-6 border-t border-[var(--ledger-rule)] pt-5 text-sm leading-6 text-[var(--muted-ink)]">
                  Keep the reference ID. A human can review this open request.{' '}
                  <span>Response time is not guaranteed.</span> For suspected fraud, contact the
                  broker now through its official channel and do not share credentials.
                </p>
              </article>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
