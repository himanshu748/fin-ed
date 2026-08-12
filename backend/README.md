# FinEd Saathi backend

This Python service is the real-time voice agent for FinEd Saathi, an English and Hindi
financial-literacy tutor in the **Financial Services** track of VoiceForBharat.
It connects to LiveKit Cloud as the named agent `my-agent`.

```text
User speech -> Deepgram Nova-3 -> Gemini + FinEd tools -> Murf Falcon 2 -> audio
```

The agent is education-only. It does not execute real trades or provide personalized
investment advice. F&O help is limited to mechanics, simulation and risk.

## Setup

From this directory:

```bash
uv sync
cp .env.example .env.local
```

Complete `.env.local` with your own credentials:

| Variable             | Purpose                                                        |
| -------------------- | -------------------------------------------------------------- |
| `LIVEKIT_URL`        | LiveKit Cloud WebSocket URL                                    |
| `LIVEKIT_API_KEY`    | LiveKit project API key                                        |
| `LIVEKIT_API_SECRET` | LiveKit project API secret                                     |
| `MURF_API_KEY`       | Murf speech synthesis                                          |
| `DEEPGRAM_API_KEY`   | Deepgram speech recognition                                    |
| `GOOGLE_API_KEY`     | Gemini conversation and optional knowledge embeddings          |
| `GEMINI_MODEL`       | Optional exact model selection; defaults to `gemini-3.5-flash-lite` |
| `FINED_MEMORY_DB_PATH` | Optional Day 4 SQLite path; defaults inside `data/memory`     |
| `FINED_ESCALATION_DB_PATH` | Optional Day 7 SQLite path; defaults inside `data/escalations` |
| `SIP_OUTBOUND_TRUNK_ID` | Optional stored LiveKit outbound SIP trunk ID (`ST_...`) for Day 6 |
| `FINED_OUTBOUND_AGENT_NAME` | Optional Day 6 worker name; defaults to `my-agent`             |
| `FINED_ESCALATION_CALLBACK_NUMBER` | Optional private Day 7 demo callback destination in E.164 format |

Do not commit `.env.local` or paste credentials into issues, logs, or docs.

Download the local Silero VAD and turn-detection model files once:

```bash
uv run python src/agent.py download-files
```

## Run

For the browser-based Day 1 session:

```bash
uv run dotenv -f .env.local run -- python src/agent.py dev
```

Then start the frontend separately and open
[http://localhost:3000](http://localhost:3000). The frontend must use the same
LiveKit Cloud project and `AGENT_NAME=my-agent`. No local LiveKit server is
required.

The production CLI mode is:

```bash
uv run dotenv -f .env.local run -- python src/agent.py start
```

## Day 6: consented outbound paper-practice reminder

The optional outbound flow is a private, operator-triggered command for one
learner who explicitly opted in to a paper-trading practice reminder. It is not
available to the browser. It creates an explicit LiveKit dispatch with
phone-free allowlisted metadata, then makes one SIP participant dial. The
outbound agent says who it is, states the opt-in reason and lets the recipient
say stop before any lesson.

The call has its own non-persistent ₹1,00,000 virtual portfolio. FinEd may use
read-only Angel One market data to prepare an NSE EQ delivery paper draft. It
must state the draft details and estimated charges then receive explicit voice
confirmation before applying a simulated buy or sell. It rejects short sales,
insufficient cash, stale drafts and drafts without verified charge estimates.
No broker order endpoint exists in this path. The call portfolio is discarded
when the session ends and is separate from the browser portfolio.

Create a stored outbound SIP trunk in LiveKit Cloud with the Twilio carrier and
Indian termination enabled. Put its `ST_...` ID in `.env.local`; the command
also uses the existing `LIVEKIT_URL`, `LIVEKIT_API_KEY` and
`LIVEKIT_API_SECRET`. Carrier credentials stay with the stored LiveKit trunk,
not this repository.

```text
SIP_OUTBOUND_TRUNK_ID=ST_your_livekit_outbound_trunk_id
# FINED_OUTBOUND_AGENT_NAME=my-agent
```

The agent-name value is optional and defaults to `my-agent`. Do not put a
recipient number in `.env.local`. Supply one Indian number in E.164 form at the
private command boundary, such as `+919876543210`; the example is a placeholder.

Before each attempt, verify a specific recorded opt-in and confirm that the
learner has not withdrawn consent. The required `--consent-confirmed` flag is
an operator attestation, not a consent database or do-not-call registry. Start
the `my-agent` worker, then run a dry run from a private interactive terminal:

```bash
uv run dotenv -f .env.local run -- python src/outbound_call.py --consent-confirmed --dry-run
```

With a safe configuration, it prints `Dry run passed. No phone call was made.`

The command prompts without echo for the Indian E.164 number, then validates
it with the stored trunk ID and agent name. It refuses pipelines and
noninteractive shells so the number does not enter command arguments. The dry
run does not create a LiveKit client, dispatch or call. Only after it succeeds
and consent is checked again, place exactly one real call:

```bash
uv run dotenv -f .env.local run -- python src/outbound_call.py --consent-confirmed
```

The real command dispatches first, then dials once through the stored trunk. It
has a 25-second ringing limit and a five-minute maximum duration. It does not
log the number in its normal output, persist a contact or job, use the browser,
access a broker account or execute a real trade. It can update only the
call-scoped virtual portfolio after explicit confirmation. Busy, unanswered and
failed attempts do not retry. Do not place this command in CI, a scheduler or a
browser route.

Direct phrases such as `stop`, `hang up`, `disconnect the call`, `कॉल बंद करो`
and `फोन काट दो` bypass Gemini and remove the SIP participant immediately. The
call also closes when the recipient hangs up.

## Day 7: optional automated acknowledgement callback

The required Day 7 path saves the consented request to the local Human help
dashboard. A callback is optional. To demo one, store a private E.164 destination
as `FINED_ESCALATION_CALLBACK_NUMBER` in `.env.local`, restart the worker, create
a request and then ask FinEd Saathi to call you about that reference.

FinEd explains that the callback is automated and not a human adviser. It asks
for fresh permission immediately before the callback tool runs. Refusing
permission never places a call. Only a reference created in the current browser
session can trigger one attempt, and the number never enters model arguments,
browser state, dispatch metadata or application logs.

## Voice and model configuration

The Day 1 Indian voice is configured in `src/agent.py`:

| Setting | Value            |
| ------- | ---------------- |
| Voice   | `Nikhil`         |
| Style   | `Conversational` |
| Locale  | `en-IN`          |
| Model   | `falcon-2`       |

Speech recognition uses Deepgram Nova-3 with `language="multi"` and 100 ms
endpointing for English/Hindi code-switching. The agent answers in concise
Indian English and Hindi.

The Gemini policy lives in `src/fined/chat_model.py`. Its default is
`gemini-3.5-flash-lite`; the only explicit alternatives are
`gemini-3.6-flash` and `gemini-2.5-flash`. Empty, padded, or unknown model
values fail safely. The service does not silently fall back to another model.

Both Gemini 3.x choices use minimal thinking. Gemini 2.5 uses a bounded
128-token thinking budget so tool-call thought signatures remain valid. Every
choice caps output at 320 tokens, and deprecated Gemini 3.x sampling fields are
not sent. Provider errors are converted to fixed safe messages before they
reach application logs or agent error events.

## FinEd behavior

The browser sends one sanitized learning mode in participant metadata:

- Stocks
- Mutual Funds & SIPs
- ETFs
- Gold
- F&O
- IPOs
- Bonds
- General / Ask Anything

`src/fined/agent.py` builds the mode-specific greeting, system prompt, and
tools. The delivery calculator is limited to its documented delivery assumptions
and is not used for intraday or F&O charges. The canonical Day 1 prompt is:

> Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua.

The remembered ₹50 stays unresolved until the user identifies whether it came
from the contract note, ledger or available funds, or P&L.

## Persistent caller memory

The token endpoint creates one anonymous learner ID and keeps it in an HttpOnly
browser cookie. The backend uses that ID only as the key for a local SQLite
record. At the start of every call, Gemini must invoke `lookup_caller_memory`
before it greets the learner.

`save_caller_memory` requires an explicit yes for that exact save. It accepts a
name, an English or Hindi preference and two to four allowlisted learning facts.
The schema does not accept account or identity fields. `forget_caller_memory`
also requires a clear yes before it deletes the record.

The default database is `data/memory/fined.sqlite3`. It is excluded from Git and
persists across agent restarts. Set `FINED_MEMORY_DB_PATH` only when a different
private local path is needed.

## Day 7 consented human help

The browser agent can create one of two human-help request types:
`suspected_fraud` or `decision_review`. It never decides that fraud is proven.
For suspected fraud it first checks whether the learner recognises or authorised
the reported activity. Ordinary losses, returns, market questions and charge
disputes do not qualify by themselves.

Browser paper orders above ₹50,000 fail closed before draft creation and can be
offered as a consented `decision_review` request. This is a paper-trading safety
threshold and never creates or authorises a real broker order.

`create_escalation` requires fresh explicit consent for the exact summary being
shared. The SQLite service accepts only bounded allowlisted fields and removes
OTPs, PINs, passwords, PANs, Aadhaar values and long account-number patterns.
It stores an anonymous caller fingerprint only for duplicate protection. Public
request objects contain no caller ID or transcript.

The default private queue is `data/escalations/fined.sqlite3`. It is excluded
from Git and can be moved with `FINED_ESCALATION_DB_PATH`. After creation the
agent sends the public request only to the connected learner through a scoped
LiveKit RPC. The browser opens the Human help view and displays the reference ID,
status, urgency, safe summary, completed checks and honest next step.

## Knowledge-index behavior

The Day 1 voice session does not require a published knowledge index. When
`data/knowledge/generated/current` is genuinely absent, startup emits a fixed
warning and installs an unavailable retriever whose searches return no evidence.
The knowledge tool then tells the agent that evidence is unavailable, so it
cannot invent a source-backed answer.

If `current` exists—including as a broken symlink or malformed pointer—the
backend attempts to load it and propagates the validation failure. This keeps a
bad build distinct from an index that has never been published.

Generated index artifacts are rebuildable and ignored by Git; the source
manifest remains in `data/knowledge/sources.json`.

Build the allowlisted sources and publish a local hybrid index:

```bash
uv run python -m fined.knowledge.ingest
```

Verify that the published index returns attributable evidence for representative
ETF, DP-charge, SIP, gold-tax, and F&O-risk questions:

```bash
uv run python -m fined.knowledge.verify
```

Both commands load `GOOGLE_API_KEY` from `.env.local`. A required source failure
aborts publication, and generated builds remain excluded from Git.

## Read-only Angel One market data and MCP

The optional market-data gateway uses Angel One SmartAPI's official LTP,
instrument-search and historical-candle endpoints. Add all five `ANGEL_ONE_*`
values shown in `.env.example` to `.env.local`; when any value is absent or
invalid, market-data lookup fails closed without affecting the voice tutor.
Access tokens expire according to the broker's authentication policy. Generate
the current token locally from the `backend` directory:

```bash
uv run python -m fined.market_data.session_setup
```

The command reads the API key and network headers from `.env.local`, prompts
without echo for the Angel One PIN and TOTP, sends them directly to Angel One,
and atomically saves only the returned access token. It never stores the client
ID, PIN, TOTP, refresh token, or feed token. Restart the agent worker after a
successful refresh.

Run the local stdio MCP server with:

```bash
uv run python -m fined.market_data.mcp_server
```

It exposes only `get_market_quote(exchange, symbol_token)` and
`search_market_instruments(query, exchange, limit)`. Both tools are marked
read-only and have no account, holding, position, recommendation or order
capability. MCP supplies the tool interface while Angel One supplies the
authenticated market data.

Historical data stays inside the voice agent through
`calculate_historical_return`. The tool requires an instrument resolved by
search, a purchase date, a valuation date and an investment amount. It fetches
two bounded `ONE_DAY` candle windows, uses whole units and retains leftover
cash. The result includes actual provider dates and prices plus a fixed warning
that dividends, splits, bonus issues, fees, taxes and inflation are excluded.
The endpoint cannot read broker trade history or place an order.

## Tests

Run the deterministic suite without provider-backed evaluations:

```bash
uv run pytest -q --ignore=tests/test_agent.py
```

Run the focused model-policy test:

```bash
uv run pytest tests/test_chat_model.py -q
```

Check lint and formatting:

```bash
uv run ruff check .
uv run ruff format --check .
```

`tests/test_agent.py` uses LiveKit Inference as an LLM and judge, so that
separate suite requires provider access:

```bash
uv run pytest tests/test_agent.py -q
```

## Layout

```text
backend/
├── src/agent.py                       # Agent server and session lifecycle
├── src/fined/
│   ├── agent.py                       # Prompt, profile, greeting, and tools
│   ├── calculator.py                  # Deterministic delivery illustration
│   ├── historical_returns.py          # Whole-unit past-return illustration
│   ├── chat_model.py                  # Gemini allowlist and output policy
│   ├── provider_safety.py             # Safe provider-error boundary
│   ├── speech.py                      # Spoken rendering and URL handling
│   └── knowledge/                     # Extraction, ingestion, and retrieval
├── data/knowledge/sources.json        # Curated source manifest
├── tests/                             # Contracts, unit tests, and evals
├── .env.example                       # Credential template
└── pyproject.toml                     # Dependencies and tool configuration
```

## References

- [Murf Falcon 2](https://murf.ai/api/docs/text-to-speech-models/falcon-2)
- [LiveKit Agents](https://docs.livekit.io/agents/)
- [Deepgram Nova-3](https://developers.deepgram.com/docs/models-languages-overview)
- [Gemini models](https://ai.google.dev/gemini-api/docs/models)

## License

MIT — see the repository's `LICENSE` file.
