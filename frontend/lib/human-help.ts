export const HUMAN_HELP_RPC_METHOD = 'fined.escalation.v1.show_request';
export const MAX_HUMAN_HELP_RPC_BYTES = 8_000;

export type HumanHelpReason = 'suspected_fraud' | 'decision_review';
export type HumanHelpUrgency = 'low' | 'medium' | 'high' | 'emergency';
export type HumanHelpLanguage = 'english' | 'hindi' | 'bilingual';

export interface HumanHelpRequest {
  version: 1;
  reference_id: string;
  reason: HumanHelpReason;
  summary: string;
  checks_completed: string;
  urgency: HumanHelpUrgency;
  language: HumanHelpLanguage;
  follow_up_method: 'in_app';
  status: 'open';
  created_at: string;
}

const EXACT_KEYS = [
  'version',
  'reference_id',
  'reason',
  'summary',
  'checks_completed',
  'urgency',
  'language',
  'follow_up_method',
  'status',
  'created_at',
] as const;
const REFERENCE_ID = /^HELP-[A-Z0-9](?:[A-Z0-9-]{6,62})[A-Z0-9]$/;
const PAN = /\b[A-Z]{5}[0-9]{4}[A-Z]\b/i;
const LONG_NUMBER = /(?<!\d)(?:\d[ -]?){8,}\d?(?!\d)/;
const LABELLED_SECRET =
  /\b(?:otp|pin|password|passcode|aadhaar|aadhar|account\s+number|client\s+id)\b\s*(?:is|was|:|=|-)\s*[A-Za-z0-9@#$%^&*._/-]{3,}/i;

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function boundedText(value: unknown, field: string, maximumBytes: number): string {
  if (typeof value !== 'string' || value.trim() !== value || value.length === 0) {
    throw new Error(`${field} must be non-empty trimmed text`);
  }
  if (byteLength(value) > maximumBytes || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error(`${field} is outside the safe size`);
  }
  if (PAN.test(value) || LONG_NUMBER.test(value) || LABELLED_SECRET.test(value)) {
    throw new Error(`${field} contains private information`);
  }
  return value;
}

function exactObject(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('Human-help payload must be an object');
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== EXACT_KEYS.length || keys.some((key) => !EXACT_KEYS.includes(key as never))) {
    throw new Error('Human-help payload has an invalid shape');
  }
  return record;
}

export function decodeHumanHelpRequest(payload: string): HumanHelpRequest {
  if (typeof payload !== 'string' || byteLength(payload) > MAX_HUMAN_HELP_RPC_BYTES) {
    throw new Error('Human-help payload exceeds the maximum size');
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    throw new Error('Human-help payload must be valid JSON');
  }
  const value = exactObject(decoded);
  if (value.version !== 1) throw new Error('Human-help payload version is unsupported');
  if (typeof value.reference_id !== 'string' || !REFERENCE_ID.test(value.reference_id)) {
    throw new Error('Human-help reference ID is invalid');
  }
  if (value.reason !== 'suspected_fraud' && value.reason !== 'decision_review') {
    throw new Error('Human-help reason is invalid');
  }
  if (!['low', 'medium', 'high', 'emergency'].includes(String(value.urgency))) {
    throw new Error('Human-help urgency is invalid');
  }
  if (!['english', 'hindi', 'bilingual'].includes(String(value.language))) {
    throw new Error('Human-help language is invalid');
  }
  if (value.follow_up_method !== 'in_app' || value.status !== 'open') {
    throw new Error('Human-help follow-up or status is invalid');
  }
  if (
    typeof value.created_at !== 'string' ||
    !/(?:Z|[+-]\d{2}:\d{2})$/.test(value.created_at) ||
    !Number.isFinite(Date.parse(value.created_at))
  ) {
    throw new Error('Human-help timestamp is invalid');
  }

  return {
    version: 1,
    reference_id: value.reference_id,
    reason: value.reason,
    summary: boundedText(value.summary, 'summary', 480),
    checks_completed: boundedText(value.checks_completed, 'checks completed', 900),
    urgency: value.urgency as HumanHelpUrgency,
    language: value.language as HumanHelpLanguage,
    follow_up_method: 'in_app',
    status: 'open',
    created_at: value.created_at,
  };
}

export function createHumanHelpRpcHandler(
  expectedAgentIdentity: string,
  showRequest: (request: HumanHelpRequest) => void
) {
  if (!expectedAgentIdentity.trim()) throw new Error('Expected agent identity is required');
  return async ({ callerIdentity, payload }: { callerIdentity: string; payload: string }) => {
    if (callerIdentity !== expectedAgentIdentity) {
      throw new Error('Human-help RPC caller is not authorized');
    }
    const request = decodeHumanHelpRequest(payload);
    showRequest(request);
    return JSON.stringify({ version: 1, opened: true });
  };
}
