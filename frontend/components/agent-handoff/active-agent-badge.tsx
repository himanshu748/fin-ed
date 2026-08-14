'use client';

import { useAgentHandoff } from '@/components/agent-handoff/agent-handoff-provider';

export function ActiveAgentBadge() {
  const { activeAgent } = useAgentHandoff();

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-11 min-w-0 items-center gap-2 rounded-[10px] border border-[var(--ledger-blue)] bg-[var(--blue-wash)] px-3 text-sm text-[var(--ledger-ink)]"
    >
      <span aria-hidden="true" className="size-2 shrink-0 rounded-[2px] bg-[var(--ledger-blue)]" />
      <span className="min-w-0">
        <span className="font-semibold">{activeAgent.display_name}</span>
        <span className="text-[var(--muted-ink)]"> · {activeAgent.voice_name}</span>
        {activeAgent.specialty && (
          <span className="block truncate text-xs text-[var(--muted-ink)] sm:inline sm:before:pr-1 sm:before:content-['·']">
            {activeAgent.specialty}
          </span>
        )}
      </span>
    </div>
  );
}
