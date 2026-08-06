# FinEd Saathi contributor guide

FinEd Saathi is a voice-first Hinglish tutor for beginner concepts in the Indian
financial market. It is the Financial Services track project for VoiceForBharat.
Treat it as an education product: it must not place trades, provide calls or
targets, promise returns, or give personalized investment advice.

## Product contracts

Preserve these behaviors unless a task explicitly changes the product contract
and updates its tests:

- The eight modes are Stocks, Mutual Funds & SIPs, ETFs, Gold, F&O, IPOs,
  Bonds, and Ask Anything.
- F&O is education and simulation only, with a prominent risk warning and no
  live strategy.
- The canonical starter question is: “Maine ₹6 mein stock liya, ₹6 mein hi bech
  diya, phir bhi mujhe ₹50 ka loss hua.” The remembered ₹50 remains unresolved
  until the user identifies whether it appeared in the contract note, ledger or
  available funds, or P&L.
- The delivery calculator is schedule-backed and delivery-only. Do not use it
  for intraday or F&O, reconstruct fee arithmetic in the LLM, or imply that each
  buy and sell always costs ₹20 plus GST.
- The Day 1 voice is Murf `Nikhil`, style `Conversational`, locale `en-IN`, model
  `falcon-2`.
- The configured Gemini default is `gemini-3.6-flash`. Only
  `gemini-3.5-flash-lite` and `gemini-2.5-flash` may be selected explicitly.
  Unknown, empty, or padded values fail safely; there is no cross-model fallback.
- Gemini 3.x uses minimal thinking, Gemini 2.5 uses a zero thinking budget, and
  all choices cap output at 320 tokens. Keep provider errors behind the fixed
  safe error boundary.

## Repository map

```text
fin-ed/
├── backend/
│   ├── src/agent.py                  # LiveKit server and STT/LLM/TTS lifecycle
│   ├── src/fined/agent.py            # Prompt, modes, greeting, and tools
│   ├── src/fined/calculator.py       # Delivery-charge calculation
│   ├── src/fined/chat_model.py       # Gemini policy
│   ├── src/fined/provider_safety.py  # Provider-error sanitization
│   ├── src/fined/knowledge/          # Ingestion and retrieval
│   ├── data/knowledge/sources.json   # Curated source manifest
│   └── tests/                        # Unit, contract, lifecycle, and eval tests
├── frontend/
│   ├── app/                          # Next.js pages and token route
│   ├── components/app/               # FinEd landing and live-session views
│   ├── components/agents-ui/         # Voice and transcript controls
│   ├── lib/learning-modes.ts         # Eight-mode metadata contract
│   └── tests/                        # Design, metadata, and token security tests
└── docs/DESIGN.md                    # Finance product design system
```

## Backend workflow

Use Python 3.10–3.14 and `uv`; do not install project dependencies with `pip`.

```bash
cd backend
uv sync
cp .env.example .env.local
uv run python src/agent.py download-files
uv run dotenv -f .env.local run -- python src/agent.py dev
```

The backend requires LiveKit Cloud, Murf, Deepgram, and Google credentials. Keep
all credentials in `.env.local`; never commit or print them.

Run the deterministic suite and style checks with:

```bash
cd backend
uv run pytest -q --ignore=tests/test_agent.py
uv run ruff check .
uv run ruff format --check .
```

`tests/test_agent.py` is a separate LiveKit Inference-backed evaluation suite.
Run it only when provider access is available:

```bash
uv run pytest tests/test_agent.py -q
```

When changing prompts, tools, provider setup, or lifecycle behavior, add or
update deterministic contract tests. Do not replace fixed safety assertions with
LLM-judge-only coverage.

## Day 1 knowledge behavior

The published knowledge index is optional for the Day 1 voice conversation. If
`backend/data/knowledge/generated/current` is genuinely absent, startup uses
`UnavailableKnowledgeRetriever`; searches return no evidence and the tool tells
the agent not to guess.

If `current` exists as a directory, symlink, broken symlink, or malformed
pointer, the backend must attempt normal validation and propagate any failure.
Never hide a corrupt index by treating it as intentionally absent.

Generated index builds are ignored by Git. Keep the source manifest and tests
tracked. Embeddings use `gemini-embedding-001` at 768 dimensions; changing that
contract requires rebuilding and validating the versioned artifacts.

## Frontend workflow

Use the repository's pinned pnpm version.

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

The frontend must use the same LiveKit Cloud project as the backend and
`AGENT_NAME=my-agent`.

Verify frontend changes with:

```bash
cd frontend
node --test tests/*.test.mjs
pnpm exec tsc --noEmit
pnpm format:check
pnpm build
```

Follow `docs/DESIGN.md` for product UI work. Keep all eight modes accessible by
keyboard, preserve the pre-connect F&O warning, and retain fixed safe error copy
instead of exposing provider or token-service details.

## Token endpoint security

`frontend/app/api/token/route.ts` contains a development token issuer. Its
security properties are part of the tested contract:

- It accepts `POST` only for direct local development by default: `pnpm dev`
  binds to `127.0.0.1`; `Host` and Next.js's synthesized forwarding fields must
  describe one coherent loopback request. Public, conflicting, malformed, RFC
  `Forwarded`, and unknown `X-Forwarded-*` values are rejected.
- Production requests are rejected even with a loopback-looking `Host` unless
  the exact unsafe demo opt-in is enabled.
- `LIVEKIT_API_SECRET` remains server-only. Never expose it through a
  `NEXT_PUBLIC_` variable, response, log, or client component.
- Agent dispatch is server-owned through `AGENT_NAME`; callers cannot choose an
  agent, room, participant identity, or participant name.
- The only accepted caller-controlled request field is `participant_metadata`.
  Its JSON string is bounded and sanitized to an object containing one
  allowlisted `learning_mode`; invalid input falls back to `general`.
- Rooms and participant identities are generated server-side, token lifetime is
  15 minutes, and success and error responses use `Cache-Control: no-store`.
- Errors return and log fixed generic messages without raw exceptions or secret
  values.

`UNSAFE_ALLOW_UNAUTHENTICATED_PUBLIC_TOKEN_ENDPOINT=true` deliberately bypasses
the development, direct-connection, and loopback checks. Use it only for an
intentional short-lived demo. Replace the bundled endpoint with an
authenticated, authorized, rate-limited token service before a public
deployment.

## Change discipline

- Preserve unrelated work in a dirty tree and keep changes scoped to the task.
- Add tests alongside behavior changes and run the smallest focused test first,
  then the relevant full suite.
- Do not weaken source precedence, financial safety, metadata sanitation,
  provider-error sanitation, or credential handling to make a test pass.
- Do not commit generated indexes, local environment files, browser recordings,
  screenshots, caches, or internal planning artifacts.
- Run `git diff --check` before handing off a change.

## References

- [Murf Falcon 2](https://murf.ai/api/docs/text-to-speech-models/falcon-2)
- [Murf voice library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents](https://docs.livekit.io/agents/)
- [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Deepgram Nova-3](https://developers.deepgram.com/docs/models-languages-overview)
