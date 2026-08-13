export type CallChannel = 'browser' | 'sip';
export type CallOutcome = 'successful' | 'failed';
export type CallDetail =
  | 'grounded_answer_delivered'
  | 'market_quote_delivered'
  | 'historical_return_calculated'
  | 'paper_fill_completed'
  | 'human_help_created'
  | 'no_completed_action'
  | 'incomplete'
  | 'no_response'
  | 'tool_unavailable'
  | 'system_error';

export interface CallAnalyticsSummary {
  version: 1;
  success_definition: string;
  totals: {
    total_calls: number;
    successful_calls: number;
    failed_calls: number;
    success_rate_percent: number;
  };
  recent_calls: Array<{
    call_id: string;
    started_at: string;
    duration_seconds: number;
    channel: CallChannel;
    outcome: CallOutcome;
    detail: CallDetail;
  }>;
}

const SUMMARY_KEYS = ['recent_calls', 'success_definition', 'totals', 'version'] as const;
const TOTAL_KEYS = [
  'failed_calls',
  'success_rate_percent',
  'successful_calls',
  'total_calls',
] as const;
const CALL_KEYS = [
  'call_id',
  'channel',
  'detail',
  'duration_seconds',
  'outcome',
  'started_at',
] as const;
const CALL_ID = /^CALL-(?:[A-F0-9]{4}-){5}[A-F0-9]{4}$/;
const DETAILS = new Set<CallDetail>([
  'grounded_answer_delivered',
  'market_quote_delivered',
  'historical_return_calculated',
  'paper_fill_completed',
  'human_help_created',
  'no_completed_action',
  'incomplete',
  'no_response',
  'tool_unavailable',
  'system_error',
]);
const SUCCESS_DETAILS = new Set<CallDetail>([
  'grounded_answer_delivered',
  'market_quote_delivered',
  'historical_return_calculated',
  'paper_fill_completed',
  'human_help_created',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === keys[index]);
}

function safeCount(value: unknown): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) throw new Error('Invalid call count');
  return Number(value);
}

export function emptyCallAnalyticsSummary(): CallAnalyticsSummary {
  return {
    version: 1,
    success_definition:
      'The learner completed a verified action using grounded evidence, trusted data, paper practice or human help.',
    totals: {
      total_calls: 0,
      successful_calls: 0,
      failed_calls: 0,
      success_rate_percent: 0,
    },
    recent_calls: [],
  };
}

export function decodeCallAnalyticsSummary(value: unknown): CallAnalyticsSummary {
  if (!isRecord(value) || !hasExactKeys(value, SUMMARY_KEYS) || value.version !== 1) {
    throw new Error('Invalid analytics summary');
  }
  if (
    typeof value.success_definition !== 'string' ||
    value.success_definition.length < 10 ||
    value.success_definition.length > 360
  ) {
    throw new Error('Invalid success definition');
  }
  if (!isRecord(value.totals) || !hasExactKeys(value.totals, TOTAL_KEYS)) {
    throw new Error('Invalid analytics totals');
  }
  const totalCalls = safeCount(value.totals.total_calls);
  const successfulCalls = safeCount(value.totals.successful_calls);
  const failedCalls = safeCount(value.totals.failed_calls);
  const rate = value.totals.success_rate_percent;
  if (
    successfulCalls + failedCalls !== totalCalls ||
    typeof rate !== 'number' ||
    !Number.isFinite(rate) ||
    rate < 0 ||
    rate > 100 ||
    Math.abs(rate - (totalCalls ? Math.round((successfulCalls * 1000) / totalCalls) / 10 : 0)) >
      0.001
  ) {
    throw new Error('Inconsistent analytics totals');
  }
  if (!Array.isArray(value.recent_calls) || value.recent_calls.length > 20) {
    throw new Error('Invalid recent calls');
  }
  const recentCalls = value.recent_calls.map((candidate) => {
    if (!isRecord(candidate) || !hasExactKeys(candidate, CALL_KEYS)) {
      throw new Error('Invalid recent call');
    }
    if (typeof candidate.call_id !== 'string' || !CALL_ID.test(candidate.call_id)) {
      throw new Error('Invalid call ID');
    }
    if (
      typeof candidate.started_at !== 'string' ||
      !Number.isFinite(Date.parse(candidate.started_at))
    ) {
      throw new Error('Invalid call time');
    }
    const duration = safeCount(candidate.duration_seconds);
    if (duration > 86_400) throw new Error('Invalid call duration');
    if (candidate.channel !== 'browser' && candidate.channel !== 'sip') {
      throw new Error('Invalid call channel');
    }
    const channel: CallChannel = candidate.channel;
    if (candidate.outcome !== 'successful' && candidate.outcome !== 'failed') {
      throw new Error('Invalid call outcome');
    }
    const outcome: CallOutcome = candidate.outcome;
    if (typeof candidate.detail !== 'string' || !DETAILS.has(candidate.detail as CallDetail)) {
      throw new Error('Invalid call detail');
    }
    const detail = candidate.detail as CallDetail;
    if ((outcome === 'successful') !== SUCCESS_DETAILS.has(detail)) {
      throw new Error('Inconsistent call outcome');
    }
    return {
      call_id: candidate.call_id,
      started_at: candidate.started_at,
      duration_seconds: duration,
      channel,
      outcome,
      detail,
    };
  });

  return {
    version: 1,
    success_definition: value.success_definition,
    totals: {
      total_calls: totalCalls,
      successful_calls: successfulCalls,
      failed_calls: failedCalls,
      success_rate_percent: rate,
    },
    recent_calls: recentCalls,
  };
}
