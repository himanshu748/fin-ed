# FinEd Saathi

FinEd Saathi is a voice-first English and Hindi tutor for beginner concepts in
the Indian financial market. It follows the language style the user chooses,
including user-led code-mixing. It is the **Financial Services** track project for Days 1 to 4 of
**10 Days of Voice Agents — VoiceForBharat Edition**.

The agent explains products, fees, taxes, and risks; it does not place trades or
give personalized investment advice. Its first worked example starts from a real
beginner question:

> Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua.

FinEd separates price profit and loss from transaction costs, treats the
remembered ₹50 as unresolved, and asks where that amount appeared before trying
to reconcile it.

## Days 1 to 4 build

- Eight learning modes: Stocks, Mutual Funds & SIPs, ETFs, Gold, F&O, IPOs,
  Bonds, and Ask Anything.
- A responsive Next.js interface with a visible ₹6 delivery-charge illustration
  and an education-only F&O warning.
- Deepgram Nova-3 multilingual speech recognition with 100 ms endpointing for
  English, Hindi, and user-led code-switching.
- Google Gemini for the conversation and tool calls.
- Murf Falcon 2 speech with `Nikhil`, `Conversational`, and Indian English
  (`en-IN`).
- Indian locale metadata and transcript-time formatting (`en-IN`).
- LiveKit Cloud for the real-time browser-to-agent session.
- A polished Day 3 frontend with visible voice states, responsive controls,
  accessible motion and an integrated paper-practice workspace.
- Day 4 persistent caller memory backed by SQLite and a server-issued anonymous
  learner ID that remains stable across calls.
- Tool-based lookup, consent-gated saving and a caller-controlled forget tool.

The F&O mode teaches mechanics and risk only. It does not provide calls or a
strategy for a live trade.

### Day 2 persona and guardrails

- A named Indian financial-literacy tutor with explicit identity, objectives,
  knowledge boundaries, speaking style, and an education-only greeting.
- English input receives English, Hindi input receives Devanagari Hindi, and a
  code-mixed turn receives a matching code-mixed response.
- A deterministic pre-LLM layer stops credentials, personalised investment
  recommendations, guaranteed outcomes, wrongdoing, and prompt extraction.
- Every refusal states the boundary, gives a short reason, and offers a safe
  educational, official-support, professional, or SEBI-registered next step.
- Ten completed adversarial checks are recorded in [RED_TEAM.md](RED_TEAM.md).

### Day 4 privacy and memory

- Every call begins with the agent invoking `lookup_caller_memory` before it
  greets the learner.
- A new learner can choose to save their name, English or Hindi preference and
  two to four learning facts such as experience level or a topic covered.
- The save tool requires a fresh explicit yes. Silence, ambiguous language or a
  previous yes cannot authorize a later write.
- Broker credentials, account numbers, PAN, Aadhaar, holdings, income and bank
  details are outside the memory schema.
- Memory lives in `backend/data/memory/fined.sqlite3` by default. The database is
  ignored by Git and survives a full agent restart.
- A consent-gated `forget_caller_memory` tool deletes the learner's record.

## Conversation flow

```text
Browser microphone
  -> LiveKit Cloud
  -> Deepgram STT
  -> Gemini + FinEd tools
  -> Murf Falcon 2 TTS
  -> LiveKit Cloud
  -> Browser audio and transcript
```

## Run locally with LiveKit Cloud

### Prerequisites

- Python 3.10–3.14
- [uv](https://docs.astral.sh/uv/)
- Node.js and pnpm 9
- LiveKit Cloud, Murf, Deepgram, and Google AI API credentials

### 1. Configure the environment

```bash
cp backend/.env.example backend/.env.local
cp frontend/.env.example frontend/.env.local
```

Fill the templates locally. The backend needs `LIVEKIT_URL`,
`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `MURF_API_KEY`, `DEEPGRAM_API_KEY`, and
`GOOGLE_API_KEY`. The frontend needs the same LiveKit project credentials and
`AGENT_NAME=my-agent`.

Never commit either `.env.local` file.

### 2. Install dependencies and voice models

```bash
cd backend
uv sync
uv run python src/agent.py download-files
```

```bash
cd frontend
pnpm install
```

### 3. Start both processes

Backend terminal:

```bash
cd backend
uv run dotenv -f .env.local run -- python src/agent.py dev
```

Frontend terminal:

```bash
cd frontend
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000), select a learning mode,
choose **Talk to FinEd Saathi**, and allow microphone access. Both processes use
the configured LiveKit Cloud project; a local LiveKit server is not required.

## Day 1 recording check

1. Keep the backend and frontend running and select **Stocks**.
2. Start the voice session and say that your track is **Financial Services**.
3. Ask: “Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka
   loss hua.”
4. Capture the transcript and Nikhil's spoken response in the screen recording.
5. Confirm the recording contains a connected session, your voice, and the
   agent's audio before posting it for the challenge.

## Day 2 recording check

1. Start in **Stocks** mode and let the agent introduce itself and its
   education-only boundary.
2. Ask the ₹6/₹50 question in Hindi or code-mixed speech, then ask one follow-up
   in English to demonstrate user-led language matching.
3. Ask for a “guaranteed F&O strategy and best stock” and record the refusal,
   risk explanation, and SEBI-registered adviser escalation.
4. Keep OTPs, PINs, passwords, account numbers, and other real private data out
   of the recording.
5. Capture both the transcript and Nikhil's Murf Falcon 2 audio.

## Day 4 recording check

1. Start a first call in any learning mode and confirm that the agent does not
   know your name.
2. Share your preferred name, language, experience level and learning goal.
3. When the agent asks whether it may remember those details, say yes clearly.
4. End the call, disconnect fully and start a second call from the same browser.
5. Record the second greeting using your name and one saved learning fact.
6. Do not share account numbers, PAN, Aadhaar, broker credentials or real
   financial details in the recording.

## Knowledge-index behavior

The curated knowledge index is optional for the Day 1 conversation. If
`backend/data/knowledge/generated/current` has never been published, the backend
starts in a fixed evidence-unavailable mode. Voice interaction remains
available, while a knowledge search returns no evidence and the agent must say
that the fact could not be verified instead of inventing an answer.

If `current` exists but is broken, malformed, or points to corrupt artifacts,
startup fails. A damaged index is never silently treated as an intentionally
absent index.

## Gemini model policy

The configured default is `gemini-3.6-flash`. `GEMINI_MODEL` may explicitly
select `gemini-3.5-flash-lite` or `gemini-2.5-flash`; other values fail safely,
and the app does not silently switch models. Gemini 3.x uses minimal thinking,
Gemini 2.5 uses a zero thinking budget, and every allowed model caps output at
320 tokens. Availability and quotas depend on the active Google project.

## Verify the project

Backend deterministic tests and formatting:

```bash
cd backend
uv run pytest -q --ignore=tests/test_agent.py
uv run ruff check .
uv run ruff format --check .
```

Frontend contract tests, types, formatting, and production build:

```bash
cd frontend
node --test tests/*.test.mjs
pnpm exec tsc --noEmit
pnpm format:check
pnpm build
```

`backend/tests/test_agent.py` is a separate provider-backed evaluation suite and
requires LiveKit Inference access.

## Project layout

```text
fin-ed/
├── backend/
│   ├── src/agent.py                  # LiveKit session and STT/LLM/TTS pipeline
│   ├── src/fined/                    # Prompt, modes, calculator, safety, knowledge
│   ├── data/knowledge/               # Source manifest and ignored generated index
│   └── tests/                        # Deterministic tests and provider-backed evals
├── frontend/
│   ├── app/                          # Next.js routes and token endpoint
│   ├── components/app/               # FinEd landing and live-session interface
│   ├── lib/learning-modes.ts         # Shared eight-mode browser contract
│   └── tests/                        # Design and participant-metadata contracts
├── RED_TEAM.md                       # Ten completed Day 2 adversarial checks
└── docs/DESIGN.md                    # Finance product design system
```

More detail is available in the [backend README](backend/README.md),
[frontend README](frontend/README.md), and [design system](docs/DESIGN.md).

## References

- [Murf Falcon 2](https://murf.ai/api/docs/text-to-speech-models/falcon-2)
- [Murf voice library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents](https://docs.livekit.io/agents/)
- [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models)
- [Deepgram Nova-3](https://developers.deepgram.com/docs/models-languages-overview)

## License

MIT
