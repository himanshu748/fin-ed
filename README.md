# FinEd Saathi

FinEd Saathi is a voice-first financial literacy tutor for Indian market concepts. It listens in English, Hindi or both then replies in the learner's language style through Murf Falcon 2 and the Indian voice Nikhil.

The project is built for the Financial Services track of **10 Days of Voice Agents - VoiceForBharat Edition**. It teaches market mechanics, charges, taxes and risks. It does not recommend securities, promise returns or place real trades.

## What works today

- Eight learning modes: Stocks, Mutual Funds & SIPs, ETFs, Gold, F&O, IPOs, Bonds and Ask Anything
- Deepgram Nova-3 multilingual speech recognition
- Google Gemini conversation and tool use with a strict model allowlist
- Murf Falcon 2 speech using `Nikhil`, `Conversational` and locale `en-IN`
- LiveKit Cloud transport with a prewarmed Python worker
- Optional Angel One SmartAPI live quotes and historical closes through read-only tools
- Whole-unit historical return illustrations with explicit corporate-action caveats
- A browser-owned paper trading ledger with ₹1,00,000 virtual cash
- Voice tools that can open the paper dashboard, prepare a simulated order and read the paper portfolio
- Visible session IDs with separate transcript history for each meaningful session
- Consent-gated caller memory backed by SQLite
- An optional local knowledge index with fail-closed evidence behavior
- A manual, consented SIP reminder with a call-scoped ₹1,00,000 paper portfolio
- Guardrails for credentials, personalised recommendations, guaranteed outcomes, wrongdoing and prompt extraction
- An accessible responsive interface with reduced-motion support

## Safety model

FinEd Saathi is an educational product. It never asks for a broker password, PIN, OTP, PAN, Aadhaar or bank details. Angel One credentials stay in the backend environment and are never sent to the browser.

Paper orders are simulated. A learner must review and explicitly confirm each draft in the browser or during an outbound practice call. No broker order API is called and no real money is used.

The optional Day 6 paper-practice reminder is started only by a private
server-side command after a learner's explicit opt-in. It creates a new LiveKit
agent dispatch before one SIP dial. The caller first hears FinEd's identity,
the opt-in purpose and a way to say stop. It has no browser, broker order or
real-trading path. It does not store a recipient number or schedule a retry.

The F&O mode explains mechanics, margin and loss risk. It does not provide signals or live strategies. Personalised decisions belong with a SEBI-registered investment adviser.

Ten adversarial checks are documented in [RED_TEAM.md](RED_TEAM.md).

## Architecture

```text
Browser microphone or typed question
  -> LiveKit Cloud
  -> Deepgram Nova-3 STT
  -> Gemini + FinEd tools and guardrails
  -> Murf Falcon 2 TTS with Nikhil
  -> LiveKit Cloud
  -> Browser audio, transcript and session archive

Optional tool paths
  -> Angel One SmartAPI for read-only NSE and BSE quotes, symbols and daily closes
  -> Browser paper ledger for simulated orders
  -> SQLite for consented caller memory
  -> Local knowledge index for cited educational evidence

Optional Day 6 outbound reminder
  -> private operator command
  -> explicit LiveKit dispatch with allowlisted, phone-free metadata
  -> one SIP participant dial through a stored LiveKit Cloud outbound trunk
  -> consented Indian E.164 recipient
  -> isolated ₹1,00,000 call-only paper ledger using read-only live quotes
```

## Run locally

### Requirements

- Python 3.10 to 3.14
- [uv](https://docs.astral.sh/uv/)
- Node.js
- pnpm 9
- LiveKit Cloud, Murf, Deepgram and Google AI credentials

Angel One SmartAPI credentials are optional. The voice tutor still works when live quotes are unavailable.

### 1. Configure environment files

```bash
cp backend/.env.example backend/.env.local
cp frontend/.env.example frontend/.env.local
```

The backend requires:

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
MURF_API_KEY
DEEPGRAM_API_KEY
GOOGLE_API_KEY
```

The frontend requires the same LiveKit project credentials plus:

```text
AGENT_NAME=my-agent
```

Never commit either `.env.local` file.

### 2. Install dependencies and local voice models

```bash
cd backend
uv sync
uv run -m livekit.agents download-files
```

The backend pins LiveKit Agents `1.6.6` and LiveKit RTC `1.1.13`. It uses the current built-in local `v1-mini` turn detector instead of the deprecated turn detector plugin.

```bash
cd frontend
pnpm install
```

### 3. Start the voice worker

For a stable demo or recording:

```bash
cd backend
uv run dotenv -f .env.local run -- python src/agent.py start
```

The production-mode worker listens for health checks on port `8081`, keeps one process warm and registers as `my-agent`.

Use `dev` instead of `start` only when you need backend file watching:

```bash
uv run dotenv -f .env.local run -- python src/agent.py dev
```

Restart the worker after changing Python dependencies. Do not rely on hot reload after replacing the LiveKit SDK inside a running process.

### 4. Start the frontend

```bash
cd frontend
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). If port 3000 is occupied, use:

```bash
pnpm dev --port 3001
```

Then open [http://127.0.0.1:3001](http://127.0.0.1:3001), select a learning mode, choose **Talk to FinEd Saathi** and allow microphone access.

## Day 5 domain tools

The primary Day 5 tool is `calculate_angel_one_trade_cost`. It computes an
Angel One equity-delivery charge estimate from a bundled local schedule snapshot.
The current snapshot applies from **1 March 2026** and records its official Angel
One, NSE, BSE and SEBI source links. This calculator does not need a broker login
or network connection. It is local schedule-backed data, not a live contract note
or account-specific result.

The tool description requires the model to collect the trade date, exchange,
quantity, buy price and optional sell details before calling it. Every result
includes its applicability date, estimate status and source links. Unsupported
dates, malformed inputs or a damaged schedule produce a fixed spoken fallback
instead of guessed charges.

The separate `get_market_quote` and `search_market_instruments` tools use live
Angel One SmartAPI data when all optional credentials below are configured. They
return the provider and exchange timestamp. If Angel One is unavailable, the
agent says live market data could not be verified and continues with the lesson.

`calculate_historical_return` uses the same market-data-only connection. It
resolves an NSE or BSE instrument, fetches two bounded daily-candle windows and
uses the first available close on or after the requested purchase date plus the
last available close on or before the valuation date. It calculates whole units,
keeps leftover cash and returns the absolute and percentage change.

Historical results are unadjusted illustrations, not total-return figures. They
exclude dividends, splits, bonus issues, fees, taxes and inflation. FinEd always
labels this limitation and never presents the result as a forecast or
recommendation.

For a Day 5 recording, ask:

> On 7 August 2026, I bought 10 shares on NSE at ₹1,400 and sold them at ₹1,450
> as a delivery trade. Use your verified Angel One calculator to explain every
> charge and tell me which schedule date you used.

To demonstrate historical data, ask:

> If I had invested ₹10,000 in Reliance on 6 January 2024, what would it have
> been worth on 7 August 2026? Use historical data and explain what the estimate
> excludes.

For the graceful failure path, ask for the same calculation with a trade date
before 1 March 2026. The agent must say that no verified schedule covers that
date and must not invent a result.

## Optional Angel One read-only market data

Create an Angel One SmartAPI app of type **Trading**. The app type provides the authenticated market data endpoints used by this project. FinEd calls only the exact quote, instrument-search and historical-candle paths. It never calls account, holding, position, trade-history or real-order endpoints.

Add these values to `backend/.env.local`:

```text
ANGEL_ONE_API_KEY
ANGEL_ONE_ACCESS_TOKEN
ANGEL_ONE_CLIENT_LOCAL_IP
ANGEL_ONE_CLIENT_PUBLIC_IP
ANGEL_ONE_MAC_ADDRESS
```

The access token must be current. If a credential is missing, expired or rejected, market-data tools fail closed and say live data is unavailable. The rest of the voice session remains usable.

Market data availability depends on Angel One access, exchange hours and the active account's entitlements. Every accepted quote is returned with its provider and exchange timestamp. Historical candles use Angel One's `ONE_DAY` interval. Paper order drafts expire 30 seconds after the quote.

## Paper trading

The paper portfolio starts with ₹1,00,000 in virtual cash and lives in browser storage. It supports simulated NSE equity buys and sells with:

- Whole positive quantities
- Fresh Angel One quote validation
- Charge estimation based on the bundled Angel One schedules
- Cash and holding checks
- A 30-second review window
- Explicit browser confirmation
- Holdings, available cash and fill history
- A reset control that restores the original virtual balance

Ask the agent to open paper trading or prepare a paper order. The LiveKit RPC bridge opens the dashboard and transfers the draft to the browser. The browser remains the source of truth for the simulated ledger.

## Day 6 consented outbound practice reminder

This optional flow is a single education-only paper-trading practice reminder,
not a campaign, scheduler or follow-up service. The only supported reminder is
`paper_practice` in Stocks mode. During the call, FinEd does not access the
browser, caller memory, a broker account or a live portfolio. It can use the
read-only market-data provider to prepare an NSE EQ delivery paper draft in an
isolated ₹1,00,000 virtual portfolio. The learner must hear the side, symbol,
quantity, timestamped price and estimated charges then explicitly confirm the
same draft before a simulated fill. The call portfolio disappears when the
call ends and never reaches a broker order API.

FinEd must end the call immediately if the recipient says stop, hang up,
disconnect the call, unsubscribe, do not call or an equivalent supported Hindi
phrase. This deterministic path runs before Gemini so it does not depend on the
model choosing a tool.

The operator must have a recorded, specific opt-in for this reminder and must
reconfirm that it has not been withdrawn before every manual attempt. The
required `--consent-confirmed` flag is an operator attestation, not a consent
database or do-not-call registry. The outbound helper keeps the phone number
out of command arguments and dispatch metadata and has no contact store, job
store or automatic retry. A busy, unanswered or failed dial ends the attempt.
A later call requires a new manual command after consent is checked again.

### Private configuration

Configure a stored outbound SIP trunk in LiveKit Cloud with the Twilio carrier,
then add its LiveKit trunk ID to `backend/.env.local`. The existing
`LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` remain required.
The optional agent-name setting defaults to the registered `my-agent` worker.

```text
SIP_OUTBOUND_TRUNK_ID=ST_your_livekit_outbound_trunk_id
# FINED_OUTBOUND_AGENT_NAME=my-agent
```

Use an Indian recipient number in E.164 form, such as `+919876543210`, with no
spaces or punctuation. The example is a placeholder. Do not put recipient
numbers in environment files, browser code, source control or tickets.

### Operator runbook

Start the backend worker first. From `backend`, run this only in a private
interactive terminal. It prompts for the Indian E.164 recipient number without
echoing it, then validates the number format and private outbound configuration
without creating a LiveKit client, dispatch or SIP call:

```bash
uv run dotenv -f .env.local run -- python src/outbound_call.py --consent-confirmed --dry-run
```

With a safe configuration, the dry run prints `Dry run passed. No phone call
was made.`

Only after a successful dry run and a fresh consent check, omit `--dry-run` for
one real attempt:

```bash
uv run dotenv -f .env.local run -- python src/outbound_call.py --consent-confirmed
```

The real command creates the explicit LiveKit dispatch first, then makes one
SIP dial through the stored trunk. It uses a 25-second ringing limit and a
five-minute maximum call duration. Normal output contains a generic outcome,
not the phone number. It refuses pipelines and noninteractive shells. Never run
this command from the browser, CI, a scheduler or an automatic retry job.

## Session history and memory

These are separate features:

- **Session history** stores meaningful transcripts in browser storage under their visible session IDs. Open **Sessions** during a call to switch between archived conversations. Empty connection attempts are not saved.
- **Caller memory** stores only consented profile facts in `backend/data/memory/fined.sqlite3`. A learner can ask what is remembered or ask FinEd to forget it.

The anonymous learner ID remains stable in the same browser. Clearing browser storage creates a new local identity and removes browser session history. The SQLite database is ignored by Git and survives agent restarts.

## Knowledge index

The curated knowledge index is optional. If `backend/data/knowledge/generated/current` has never been published, the agent starts in evidence-unavailable mode and keeps voice interaction available. A knowledge search then returns no evidence instead of inventing an answer.

If `current` exists but is broken, malformed or points to corrupt artifacts, startup fails. A damaged index is never treated as an intentionally absent index.

## Gemini model policy

The configured default is the quota-efficient `gemini-3.5-flash-lite`. `GEMINI_MODEL` can explicitly select `gemini-3.6-flash` or `gemini-2.5-flash`. Other values fail safely and the app does not silently switch models.

Gemini 3.x uses minimal thinking. Gemini 2.5 uses a bounded 128-token thinking budget so tool-call thought signatures remain valid. Every allowed model caps output at 320 tokens. Availability and quota depend on the active Google project.

## Recording checklist

1. Start the backend in `start` mode and wait for `registered worker` in the log.
2. Start the frontend and open the active port.
3. Choose a learning mode then start a voice session.
4. Confirm the UI shows a session ID and the state changes to **Listening** or **Speaking**.
5. Ask one Indian market concept such as "What is an ETF?"
6. Ask a historical return question and show the daily-close limitation.
7. Ask FinEd to open paper trading and prepare one simulated order if live quotes are configured.
8. Show the transcript, cited sources, Nikhil's audio and the education-only boundary.
9. Keep real credentials and financial identifiers out of the recording.

## Verify the project

Backend deterministic tests and formatting:

```bash
cd backend
uv run pytest -q --ignore=tests/test_agent.py
uv run ruff check .
uv run ruff format --check .
```

Frontend contract tests, types, formatting and production build:

```bash
cd frontend
node --test tests/*.test.mjs
pnpm exec tsc --noEmit
pnpm format:check
pnpm build
```

`backend/tests/test_agent.py` is a provider-backed evaluation suite and requires LiveKit Inference access.

## Project layout

```text
fin-ed/
├── backend/
│   ├── src/agent.py                  # LiveKit session and voice pipeline
│   ├── src/fined/                    # Tutor, tools, safety, memory and market data
│   ├── data/knowledge/               # Source manifest and ignored generated index
│   └── tests/                        # Deterministic tests and provider evaluations
├── frontend/
│   ├── app/                          # Next.js routes and token endpoint
│   ├── components/app/               # Landing page and live voice workspace
│   ├── components/paper-trading/     # Simulated portfolio interface
│   ├── lib/voice-session-history.ts  # Per-session transcript archive
│   └── tests/                        # UI, motion and contract tests
├── RED_TEAM.md                       # Day 2 adversarial checks
└── docs/DESIGN.md                    # Finance product design system
```

More detail is available in the [backend README](backend/README.md), [frontend README](frontend/README.md) and [design system](docs/DESIGN.md).

## References

- [Murf Falcon 2](https://murf.ai/api/docs/text-to-speech-models/falcon-2)
- [Murf voice library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents](https://docs.livekit.io/agents/)
- [LiveKit server options](https://docs.livekit.io/agents/server/options/)
- [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models)
- [Deepgram Nova-3](https://developers.deepgram.com/docs/models-languages-overview)
- [Angel One SmartAPI](https://smartapi.angelone.in/)

## License

MIT
