export const LEARNING_MODES = [
  { value: 'stocks', label: 'Stocks', helper: 'Shares, orders & charges' },
  { value: 'mutual_funds', label: 'Mutual Funds & SIPs', helper: 'Funds, SIPs & expense ratios' },
  { value: 'etfs', label: 'ETFs', helper: 'Index funds traded like shares' },
  { value: 'gold', label: 'Gold', helper: 'Physical, digital, ETF & SGB' },
  { value: 'fno', label: 'F&O', helper: 'High-risk derivatives, education only' },
  { value: 'ipos', label: 'IPOs', helper: 'Applications, allotment & listing' },
  { value: 'bonds', label: 'Bonds', helper: 'Interest, yield & credit risk' },
  { value: 'general', label: 'Ask Anything', helper: 'Any Indian-market concept' },
] as const;

export type LearningMode = (typeof LEARNING_MODES)[number]['value'];

const DEFAULT_PARTICIPANT_METADATA = participantMetadataForLearningMode('general');
const MAX_PARTICIPANT_METADATA_BYTES = 1024;

export const SANDBOX_CONNECTION_ERROR_MESSAGE = 'Unable to fetch connection details.';

interface SandboxConnectionResponse {
  ok: boolean;
  json(): Promise<unknown>;
}

interface SandboxConnectionDetails {
  serverUrl: string;
  participantToken: string;
}

export function participantMetadataForLearningMode(mode: LearningMode): string {
  return JSON.stringify({ learning_mode: mode });
}

export function isLearningMode(value: unknown): value is LearningMode {
  return LEARNING_MODES.some((mode) => mode.value === value);
}

export function sanitizeParticipantMetadata(value: unknown): string {
  if (
    typeof value !== 'string' ||
    new TextEncoder().encode(value).byteLength > MAX_PARTICIPANT_METADATA_BYTES
  ) {
    return DEFAULT_PARTICIPANT_METADATA;
  }

  try {
    const parsed: unknown = JSON.parse(value);

    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      Array.isArray(parsed) ||
      Object.keys(parsed).length !== 1 ||
      !Object.prototype.hasOwnProperty.call(parsed, 'learning_mode')
    ) {
      return DEFAULT_PARTICIPANT_METADATA;
    }

    const mode = (parsed as Record<string, unknown>).learning_mode;
    return isLearningMode(mode)
      ? participantMetadataForLearningMode(mode)
      : DEFAULT_PARTICIPANT_METADATA;
  } catch {
    return DEFAULT_PARTICIPANT_METADATA;
  }
}

export function participantMetadataRequest(participantMetadata: string | undefined): {
  participant_metadata: string | undefined;
} {
  return { participant_metadata: participantMetadata };
}

export function sanitizeParticipantMetadataRequest(body: unknown): string {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return DEFAULT_PARTICIPANT_METADATA;
  }

  const participantMetadata = Object.prototype.hasOwnProperty.call(body, 'participant_metadata')
    ? (body as Record<string, unknown>).participant_metadata
    : undefined;

  return sanitizeParticipantMetadata(participantMetadata);
}

export async function readSandboxConnectionResponse(
  response: SandboxConnectionResponse
): Promise<SandboxConnectionDetails> {
  if (!response.ok) {
    throw new Error(SANDBOX_CONNECTION_ERROR_MESSAGE);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error(SANDBOX_CONNECTION_ERROR_MESSAGE);
  }

  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    throw new Error(SANDBOX_CONNECTION_ERROR_MESSAGE);
  }

  const record = body as Record<string, unknown>;
  const serverUrl = record.serverUrl ?? record.server_url;
  const participantToken = record.participantToken ?? record.participant_token;

  if (
    typeof serverUrl !== 'string' ||
    serverUrl.trim().length === 0 ||
    typeof participantToken !== 'string' ||
    participantToken.trim().length === 0
  ) {
    throw new Error(SANDBOX_CONNECTION_ERROR_MESSAGE);
  }

  return { serverUrl, participantToken };
}
