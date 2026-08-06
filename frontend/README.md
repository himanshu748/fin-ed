# FinEd Saathi frontend

This Next.js interface connects the FinEd Saathi voice tutor to LiveKit for Day 1 of
VoiceForBharat. It presents eight Indian-market learning modes:

- Stocks
- Mutual Funds & SIPs
- ETFs
- Gold
- F&O (education only)
- IPOs
- Bonds
- Ask Anything

The UI includes the ₹6 stock charge illustration, mode-specific safety copy, a live transcript,
and browser voice controls.

## Run locally

Install dependencies and create the local environment file:

```bash
pnpm install
cp .env.example .env.local
```

Set the same LiveKit project credentials used by the backend:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
AGENT_NAME=my-agent
```

Start the frontend:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). The development command binds Next.js to
`127.0.0.1`; start the backend agent separately before opening a voice session.

## Token endpoint safety

`/api/token` is an unauthenticated development endpoint. Without an explicit opt-in, it issues a
token only when all of these conditions hold:

- `NODE_ENV=development`
- the request protocol is HTTP or HTTPS and the `Host` header is loopback (`localhost`,
  `127.0.0.1`, or `::1`)
- Next.js's synthesized `X-Forwarded-Host`, `Port`, `Proto`, and `For` values consistently describe
  that same direct loopback request

The loopback server bind is the network boundary; request headers alone cannot identify the peer.
Next.js can use a placeholder hostname in its internal request URL, so that hostname is not an
authorization signal. The route rejects the standard `Forwarded` header, unknown `X-Forwarded-*`
names, and public, conflicting, or malformed forwarding values. The server creates dispatch from
`AGENT_NAME`, and request bodies cannot choose another agent.

For an intentional, short-lived public demo, the exact value below bypasses the development,
direct-connection, and loopback checks:

```env
UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT=true
```

That escape hatch is unsafe for production. A production token service requires authentication,
authorization, and rate limiting.

## Verify

```bash
node --test tests/*.test.mjs
pnpm exec tsc --noEmit
pnpm format:check
pnpm build
```

The focused tests cover the eight-mode metadata contract, responsive design contract, server-owned
dispatch, loopback policy, forwarding-header rejection, fixed errors, and unsafe opt-in behavior.

## Key files

```text
app/api/token/route.ts       LiveKit token endpoint
components/app/              FinEd landing and session views
lib/learning-modes.ts        Eight-mode participant metadata contract
tests/                       Design, metadata, and endpoint security tests
```
