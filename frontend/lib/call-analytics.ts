export type CallChannel = 'browser' | 'sip';
export type CallOutcome = 'successful' | 'failed';
export type CallDetail =
  | 'grounded_answer_delivered'
  | 'tax_rule_delivered'
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
  version: 2;
  success_definition: string;
  totals: {
    total_calls: number;
    successful_calls: number;
    failed_calls: number;
    success_rate_percent: number;
    total_duration_seconds: number;
    fined_talk_seconds: number;
    taxed_talk_seconds: number;
    handoff_count: number;
  };
  recent_calls: Array<{
    call_id: string;
    started_at: string;
    duration_seconds: number;
    channel: CallChannel;
    outcome: CallOutcome;
    detail: CallDetail;
    fined_talk_seconds: number;
    taxed_talk_seconds: number;
    handoff_count: number;
  }>;
}

const SUMMARY_KEYS = ['recent_calls', 'success_definition', 'totals', 'version'] as const;
const TOTAL_KEYS = [
  'failed_calls',
  'fined_talk_seconds',
  'handoff_count',
  'success_rate_percent',
  'successful_calls',
  'taxed_talk_seconds',
  'total_calls',
  'total_duration_seconds',
] as const;
const CALL_KEYS = [
  'call_id',
  'channel',
  'detail',
  'duration_seconds',
  'fined_talk_seconds',
  'handoff_count',
  'outcome',
  'started_at',
  'taxed_talk_seconds',
] as const;
const CALL_ID = /^CALL-(?:[A-F0-9]{4}-){5}[A-F0-9]{4}$/;
const DETAILS = new Set<CallDetail>([
  'grounded_answer_delivered',
  'tax_rule_delivered',
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
  'tax_rule_delivered',
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

function sumDoesNotExceed(values: number[], total: number): boolean {
  let sum = 0;
  for (const value of values) {
    if (value > total - sum) return false;
    sum += value;
  }
  return true;
}

export function emptyCallAnalyticsSummary(): CallAnalyticsSummary {
  return {
    version: 2,
    success_definition:
      'The learner completed a verified action using grounded evidence, trusted data, a verified tax rule, paper practice or human help.',
    totals: {
      total_calls: 0,
      successful_calls: 0,
      failed_calls: 0,
      success_rate_percent: 0,
      total_duration_seconds: 0,
      fined_talk_seconds: 0,
      taxed_talk_seconds: 0,
      handoff_count: 0,
    },
    recent_calls: [],
  };
}

export function decodeCallAnalyticsSummary(value: unknown): CallAnalyticsSummary {
  if (!isRecord(value) || !hasExactKeys(value, SUMMARY_KEYS) || value.version !== 2) {
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
  const totalDuration = safeCount(value.totals.total_duration_seconds);
  const finedTalk = safeCount(value.totals.fined_talk_seconds);
  const taxedTalk = safeCount(value.totals.taxed_talk_seconds);
  const handoffs = safeCount(value.totals.handoff_count);
  const rate = value.totals.success_rate_percent;
  if (
    successfulCalls + failedCalls !== totalCalls ||
    typeof rate !== 'number' ||
    !Number.isFinite(rate) ||
    rate < 0 ||
    rate > 100 ||
    Math.abs(rate - (totalCalls ? Math.round((successfulCalls * 1000) / totalCalls) / 10 : 0)) >
      0.001 ||
    finedTalk + taxedTalk > totalDuration + totalCalls
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
    const finedTalkSeconds = safeCount(candidate.fined_talk_seconds);
    const taxedTalkSeconds = safeCount(candidate.taxed_talk_seconds);
    const handoffCount = safeCount(candidate.handoff_count);
    if (finedTalkSeconds + taxedTalkSeconds > duration + 1) {
      throw new Error('Inconsistent call speaking time');
    }
    return {
      call_id: candidate.call_id,
      started_at: candidate.started_at,
      duration_seconds: duration,
      channel,
      outcome,
      detail,
      fined_talk_seconds: finedTalkSeconds,
      taxed_talk_seconds: taxedTalkSeconds,
      handoff_count: handoffCount,
    };
  });
  const recentSuccessfulCalls = recentCalls.filter((call) => call.outcome === 'successful').length;
  const recentFailedCalls = recentCalls.length - recentSuccessfulCalls;
  if (
    recentCalls.length > totalCalls ||
    recentSuccessfulCalls > successfulCalls ||
    recentFailedCalls > failedCalls ||
    !sumDoesNotExceed(
      recentCalls.map((call) => call.duration_seconds),
      totalDuration
    ) ||
    !sumDoesNotExceed(
      recentCalls.map((call) => call.fined_talk_seconds),
      finedTalk
    ) ||
    !sumDoesNotExceed(
      recentCalls.map((call) => call.taxed_talk_seconds),
      taxedTalk
    ) ||
    !sumDoesNotExceed(
      recentCalls.map((call) => call.handoff_count),
      handoffs
    )
  ) {
    throw new Error('Recent calls exceed analytics totals');
  }

  return {
    version: 2,
    success_definition: value.success_definition,
    totals: {
      total_calls: totalCalls,
      successful_calls: successfulCalls,
      failed_calls: failedCalls,
      success_rate_percent: rate,
      total_duration_seconds: totalDuration,
      fined_talk_seconds: finedTalk,
      taxed_talk_seconds: taxedTalk,
      handoff_count: handoffs,
    },
    recent_calls: recentCalls,
  };
}
