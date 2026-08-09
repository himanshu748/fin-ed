import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { randomUUID } from 'node:crypto';
import { isIP } from 'node:net';
import { RoomConfiguration } from '@livekit/protocol';
import { sanitizeParticipantMetadataRequest } from '@/lib/learning-modes';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const AGENT_NAME = process.env.AGENT_NAME?.trim();
const IS_DEVELOPMENT = process.env.NODE_ENV === 'development';
const ALLOW_UNAUTHENTICATED_PUBLIC_ENDPOINT =
  process.env.UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT === 'true';

const TOKEN_ERROR_MESSAGE = 'Unable to issue connection details.';
const TOKEN_ERROR_LOG = 'Token request failed.';
const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const LEARNER_COOKIE = 'fined_learner_id';
const LEARNER_COOKIE_MAX_AGE_SECONDS = 31_536_000;
const LEARNER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const NEXT_FORWARDED_HEADERS = new Set([
  'x-forwarded-for',
  'x-forwarded-host',
  'x-forwarded-port',
  'x-forwarded-proto',
]);

// don't cache the results
export const revalidate = 0;

export async function POST(req: Request) {
  try {
    if (
      !ALLOW_UNAUTHENTICATED_PUBLIC_ENDPOINT &&
      (!IS_DEVELOPMENT || !isDirectLoopbackRequest(req))
    ) {
      console.error(TOKEN_ERROR_LOG);
      return tokenErrorResponse(403);
    }

    if (LIVEKIT_URL === undefined) {
      throw new Error();
    }
    if (API_KEY === undefined) {
      throw new Error();
    }
    if (API_SECRET === undefined) {
      throw new Error();
    }
    if (AGENT_NAME === undefined || AGENT_NAME.length === 0) {
      throw new Error();
    }

    // The caller may select only sanitized participant metadata. Agent dispatch
    // is server-owned so a request cannot redirect sessions to another agent.
    const body = await req.json().catch(() => ({}));
    const metadata = sanitizeParticipantMetadataRequest(body);
    const roomConfig = RoomConfiguration.fromJson(
      { agents: [{ agentName: AGENT_NAME }] },
      { ignoreUnknownFields: true }
    );

    // The server creates an anonymous learner ID once. Its HttpOnly cookie gives
    // Day 4 memory a stable caller key without accepting identity in the body.
    const savedLearnerId = readLearnerId(req.headers);
    const learnerId = savedLearnerId ?? randomUUID();
    const participantName = 'user';
    const participantIdentity = `voice_assistant_user_${learnerId}`;
    const roomName = `voice_assistant_room_${randomUUID()}`;

    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: participantName, metadata },
      roomName,
      roomConfig
    );

    // Return connection details
    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName,
      participantToken,
    };
    const headers: Record<string, string> = { ...NO_STORE_HEADERS };
    if (savedLearnerId === undefined) {
      headers['Set-Cookie'] = learnerCookie(learnerId, new URL(req.url).protocol === 'https:');
    }
    return NextResponse.json(data, { headers });
  } catch {
    console.error(TOKEN_ERROR_LOG);
    return tokenErrorResponse(500);
  }
}

function readLearnerId(headers: Headers): string | undefined {
  const cookie = headers.get('cookie');
  if (cookie === null || cookie.length === 0 || cookie.length > 4096) {
    return undefined;
  }
  const matches = cookie
    .split(';')
    .map((part) => part.trim())
    .filter((part) => part.startsWith(`${LEARNER_COOKIE}=`))
    .map((part) => part.slice(LEARNER_COOKIE.length + 1));
  if (matches.length !== 1 || !LEARNER_ID.test(matches[0])) {
    return undefined;
  }
  return matches[0].toLowerCase();
}

function learnerCookie(learnerId: string, secure: boolean): string {
  return [
    `${LEARNER_COOKIE}=${learnerId}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Max-Age=${LEARNER_COOKIE_MAX_AGE_SECONDS}`,
    ...(secure ? ['Secure'] : []),
  ].join('; ');
}

function tokenErrorResponse(status: number) {
  return NextResponse.json({ error: TOKEN_ERROR_MESSAGE }, { status, headers: NO_STORE_HEADERS });
}

function isDirectLoopbackRequest(req: Request): boolean {
  if (!hasOnlyExpectedForwardingHeaders(req.headers)) {
    return false;
  }

  const requestUrl = new URL(req.url);
  if (requestUrl.protocol !== 'http:' && requestUrl.protocol !== 'https:') {
    return false;
  }

  const hostHeader = req.headers.get('host');
  if (hostHeader === null) {
    return false;
  }

  const host = parseAuthority(hostHeader, requestUrl.protocol);
  const forwardedHostValue = req.headers.get('x-forwarded-host');
  const forwardedFor = req.headers.get('x-forwarded-for');
  const forwardedPort = parseForwardedPort(req.headers.get('x-forwarded-port'));
  const forwardedProto = req.headers.get('x-forwarded-proto');

  if (
    host === undefined ||
    forwardedHostValue === null ||
    forwardedFor === null ||
    forwardedPort === undefined ||
    forwardedProto === null
  ) {
    return false;
  }

  const forwardedHost = parseAuthority(forwardedHostValue, requestUrl.protocol);

  return (
    forwardedHost !== undefined &&
    isLoopbackHostname(host.hostname) &&
    forwardedHost.hostname === host.hostname &&
    forwardedHost.port === host.port &&
    forwardedPort === host.port &&
    forwardedProto === requestUrl.protocol.slice(0, -1) &&
    isLoopbackForwardedFor(forwardedFor)
  );
}

function hasOnlyExpectedForwardingHeaders(headers: Headers): boolean {
  if (headers.has('forwarded')) {
    return false;
  }

  for (const name of headers.keys()) {
    const normalized = name.toLowerCase();
    if (normalized.startsWith('x-forwarded-') && !NEXT_FORWARDED_HEADERS.has(normalized)) {
      return false;
    }
  }

  return true;
}

type ParsedAuthority = {
  hostname: string;
  port: number;
};

function parseAuthority(
  authority: string,
  protocol: 'http:' | 'https:'
): ParsedAuthority | undefined {
  if (authority.trim() !== authority || /[\s/@?#\\]/.test(authority)) {
    return undefined;
  }

  try {
    const parsed = new URL(`${protocol}//${authority}`);
    return {
      hostname: normalizeHostname(parsed.hostname),
      port: parsed.port.length > 0 ? Number(parsed.port) : defaultPort(protocol),
    };
  } catch {
    return undefined;
  }
}

function isLoopbackHostname(hostname: string): boolean {
  if (hostname === 'localhost' || hostname.endsWith('.localhost') || hostname === '::1') {
    return true;
  }

  return isLoopbackIpv4(hostname);
}

function normalizeHostname(hostname: string): string {
  return hostname
    .toLowerCase()
    .replace(/^\[|\]$/g, '')
    .replace(/\.$/, '');
}

function defaultPort(protocol: 'http:' | 'https:'): number {
  return protocol === 'https:' ? 443 : 80;
}

function parseForwardedPort(value: string | null): number | undefined {
  if (value === null || !/^[1-9]\d{0,4}$/.test(value)) {
    return undefined;
  }

  const port = Number(value);
  return port <= 65_535 ? port : undefined;
}

function isLoopbackForwardedFor(value: string): boolean {
  if (value.length === 0 || value.length > 256) {
    return false;
  }

  const addresses = value.split(',').map((address) => address.trim());
  return (
    addresses.length > 0 &&
    addresses.length <= 8 &&
    addresses.every((address) => isLoopbackIpAddress(address))
  );
}

function isLoopbackIpAddress(address: string): boolean {
  if (isIP(address) === 4) {
    return isLoopbackIpv4(address);
  }

  if (isIP(address) !== 6) {
    return false;
  }

  const normalized = address.toLowerCase();
  if (normalized === '::1') {
    return true;
  }

  const mappedIpv4 = normalized.startsWith('::ffff:') ? normalized.slice(7) : '';
  return isIP(mappedIpv4) === 4 && isLoopbackIpv4(mappedIpv4);
}

function isLoopbackIpv4(address: string): boolean {
  if (isIP(address) !== 4) {
    return false;
  }

  return Number(address.split('.')[0]) === 127;
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig?: RoomConfiguration
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}
