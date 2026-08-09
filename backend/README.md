# FinEd Saathi backend

This Python service is the real-time voice agent for FinEd Saathi, an English and Hindi
financial-literacy tutor in the **Financial Services** track of VoiceForBharat.
It connects to LiveKit Cloud as the named agent `my-agent`.

```text
User speech -> Deepgram Nova-3 -> Gemini + FinEd tools -> Murf Falcon 2 -> audio
```

The agent is education-only. It does not execute trades or provide personalized
investment advice, and F&O help is limited to mechanics, simulation, and risk.

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
| `GEMINI_MODEL`       | Optional exact model selection; defaults to `gemini-3.6-flash` |
| `FINED_MEMORY_DB_PATH` | Optional Day 4 SQLite path; defaults inside `data/memory`     |

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
`gemini-3.6-flash`; the only explicit alternatives are
`gemini-3.5-flash-lite` and `gemini-2.5-flash`. Empty, padded, or unknown model
values fail safely. The service does not silently fall back to another model.

Both Gemini 3.x choices use minimal thinking. Gemini 2.5 uses a thinking budget
of zero. Every choice caps output at 320 tokens, and deprecated Gemini 3.x
sampling fields are not sent. Provider errors are converted to fixed safe
messages before they reach application logs or agent error events.

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

The optional quote gateway uses Angel One SmartAPI's official LTP endpoint. Add
all five `ANGEL_ONE_*` values shown in `.env.example` to `.env.local`; when any
value is absent or invalid, quote lookup fails closed without affecting the
voice tutor. Access tokens expire according to the broker's authentication
policy and must be refreshed outside FinEd Saathi.

Run the local stdio MCP server with:

```bash
uv run python -m fined.market_data.mcp_server
```

It exposes only `get_market_quote(exchange, symbol_token)`. The tool is marked
read-only, includes provider and exchange timestamps, and has no account,
holding, position, recommendation, or order capability. MCP supplies the tool
interface; Angel One supplies the authenticated market data.

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
