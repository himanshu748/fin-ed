export const AGENT_STATUS_RPC_METHOD = 'fined.agent.v1.status';
export const MAX_AGENT_STATUS_RPC_BYTES = 1_024;

export interface ActiveAgentStatus {
  version: 1;
  active_agent: 'fined' | 'taxed';
  display_name: 'FinEd Saathi' | 'TaxEd';
  voice_name: 'Nikhil' | 'Anusha';
  specialty: null | 'Investment Tax Specialist';
}

export const FINED_ACTIVE_AGENT_STATUS: ActiveAgentStatus = {
  version: 1,
  active_agent: 'fined',
  display_name: 'FinEd Saathi',
  voice_name: 'Nikhil',
  specialty: null,
};

export const TAXED_ACTIVE_AGENT_STATUS: ActiveAgentStatus = {
  version: 1,
  active_agent: 'taxed',
  display_name: 'TaxEd',
  voice_name: 'Anusha',
  specialty: 'Investment Tax Specialist',
};

const EXACT_KEYS = ['version', 'active_agent', 'display_name', 'voice_name', 'specialty'] as const;

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function exactObject(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('Agent status payload must be an object');
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== EXACT_KEYS.length || keys.some((key) => !EXACT_KEYS.includes(key as never))) {
    throw new Error('Agent status payload has an invalid shape');
  }
  return record;
}

export function decodeActiveAgentStatus(payload: string): ActiveAgentStatus {
  if (typeof payload !== 'string' || byteLength(payload) > MAX_AGENT_STATUS_RPC_BYTES) {
    throw new Error('Agent status payload exceeds the maximum size');
  }

  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    throw new Error('Agent status payload must be valid JSON');
  }

  const value = exactObject(decoded);
  if (
    typeof value.version !== 'number' ||
    !Number.isInteger(value.version) ||
    value.version !== 1
  ) {
    throw new Error('Agent status payload version is unsupported');
  }

  if (
    value.active_agent === 'fined' &&
    value.display_name === 'FinEd Saathi' &&
    value.voice_name === 'Nikhil' &&
    value.specialty === null
  ) {
    return FINED_ACTIVE_AGENT_STATUS;
  }

  if (
    value.active_agent === 'taxed' &&
    value.display_name === 'TaxEd' &&
    value.voice_name === 'Anusha' &&
    value.specialty === 'Investment Tax Specialist'
  ) {
    return TAXED_ACTIVE_AGENT_STATUS;
  }

  throw new Error('Agent status payload identity is invalid');
}

export function createAgentStatusRpcHandler(
  expectedAgentIdentity: string,
  applyStatus: (status: ActiveAgentStatus) => void
) {
  if (typeof expectedAgentIdentity !== 'string' || expectedAgentIdentity.trim().length === 0) {
    throw new Error('Expected agent identity is required');
  }

  return async ({ callerIdentity, payload }: { callerIdentity: string; payload: string }) => {
    if (callerIdentity !== expectedAgentIdentity) {
      throw new Error('Agent status RPC caller is not authorized');
    }
    applyStatus(decodeActiveAgentStatus(payload));
    return '{"version":1,"accepted":true}';
  };
}
