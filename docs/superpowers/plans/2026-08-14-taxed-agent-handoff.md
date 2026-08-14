# TaxEd Agent Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a consented in-session TaxEd specialist that uses Anusha to explain only officially sourced Indian investment-tax rules, including the Income-tax Act, 2025 rules in force on 14 August 2026.

**Architecture:** FinEd and TaxEd are separate LiveKit `Agent` classes inside one `AgentSession`. A two-stage server-side consent record binds each handoff to the immediately preceding permission question and fresh affirmative response. TaxEd reads a validated packaged rule registry, receives only sanitized relevant context and overrides the session TTS with Murf Anusha while the browser receives one strict active-agent status RPC.

**Tech Stack:** Python 3.12, LiveKit Agents 1.6.6, Murf Falcon 2, pytest, Ruff, Next.js 15, React 19, TypeScript, Node test runner and pnpm.

## Global Constraints

- FinEd uses Nikhil. TaxEd uses Murf voice `en-IN-anusha`, style `Conversational` and model `falcon-2`.
- TaxEd accepts only `en-IN`, `hi-IN` or `hi-LATN`. Unknown language values fall back to `en-IN`.
- A handoff requires a new explicit yes to the exact immediately preceding permission question. Silence, stale yes, unrelated yes, negation and conditional consent fail closed.
- TaxEd uses only its packaged official-source registry. It has no market quote, paper trade, broker, memory mutation, outbound call or human-help tools.
- TaxEd does not calculate personal liability, file returns, recommend transactions or provide personalized tax advice.
- Rules for tax year 2026-27 use the Income-tax Act, 2025 as amended by Finance Act, 2026. Earlier periods are identified explicitly.
- A rule is unusable after `review_due_on`. Unsupported or stale results abstain.
- Neither agent can place a real broker order.
- User-facing copy contains no Oxford commas or em dashes.
- New behavior follows strict red, green and refactor cycles.

---

## File Map

### Backend

- Create `backend/src/fined/tax_rules.py`: validated rule model, packaged loader and deterministic lookup.
- Create `backend/src/fined/data/indian_investment_tax_rules.json`: official rules and applicability metadata verified on 2026-08-14.
- Create `backend/src/fined/handoff.py`: locale mapping, pending consent state, exact affirmative validation, PII sanitizer and bounded chat-context transfer.
- Create `backend/src/fined/taxed_agent.py`: TaxEd prompt, tax lookup tool, return tools and Anusha-specific agent contract.
- Create `backend/src/fined/agent_status_bridge.py`: narrow backend-to-browser active-agent RPC.
- Modify `backend/src/fined/agent.py`: pending state, FinEd offer and handoff tools, factory injection and routing prompt.
- Modify `backend/src/agent.py`: load registry, build recursive agent factories, build Anusha TTS and install status bridge.
- Modify `backend/src/fined/call_analytics.py`: accept `tax_rule_delivered` as a privacy-safe success.
- Modify `backend/pyproject.toml`: package the tax JSON.
- Create `backend/tests/test_tax_rules.py`.
- Create `backend/tests/test_handoff.py`.
- Create `backend/tests/test_taxed_agent.py`.
- Create `backend/tests/test_agent_status_bridge.py`.
- Modify `backend/tests/test_agent_contract.py`.
- Modify `backend/tests/test_entrypoint_lifecycle.py`.
- Modify `backend/tests/test_call_analytics.py`.

### Frontend

- Create `frontend/lib/agent-handoff.ts`: strict status decoder and authorized RPC handler.
- Create `frontend/components/agent-handoff/agent-handoff-provider.tsx`: register RPC and expose active agent state.
- Create `frontend/components/agent-handoff/active-agent-badge.tsx`: accessible identity and specialist badge.
- Modify `frontend/components/app/app.tsx`: mount the provider inside the LiveKit session provider.
- Modify `frontend/components/app/fin-ed-session-view.tsx`: render active identity, voice and specialist label.
- Create `frontend/tests/agent-handoff-rpc.test.mjs`.
- Create `frontend/tests/agent-handoff-integration.test.mjs`.
- Modify `frontend/tests/view-controller.test.mjs` only where its dependency harness needs the new provider hook.

---

### Task 1: Current Official Tax Rule Registry

**Files:**
- Create: `backend/src/fined/tax_rules.py`
- Create: `backend/src/fined/data/indian_investment_tax_rules.json`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_tax_rules.py`

**Interfaces:**
- Produces: `TaxRule`, `TaxRuleRegistry`, `TaxRuleConfigurationError`, `load_packaged_tax_rules()` and `TaxRule.to_public_dict()`.
- `TaxRuleRegistry.search(query: str, *, as_of_date: date, category: str | None = None, limit: int = 4) -> list[TaxRule]` is consumed by Task 3.

- [ ] **Step 1: Write failing validation and lookup tests**

Add literal fixtures that prove exact-host HTTPS validation, effective-date filtering, `review_due_on` expiry, category filtering, deterministic ranking and public source serialization. The first test must expect the current 2026 equity query to return Section 198 before broader capital-gain rules:

```python
results = registry.search(
    "How is a long-term equity ETF gain taxed?",
    as_of_date=date(2026, 8, 14),
    category="equity_oriented_fund",
)
assert [rule.rule_id for rule in results[:2]] == [
    "ita2025_section198_equity_ltcg",
    "ita2025_equity_fund_classification",
]
assert results[0].to_public_dict()["source_link"].startswith(
    "[Income-tax Act, 2025 as amended by Finance Act, 2026](https://"
)
```

Add rejection cases for `http://`, user-info URLs, unknown hosts, missing verification dates, `review_due_on < last_verified_on`, duplicate IDs and a stale rule searched on 2026-10-01.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd backend && uv run pytest tests/test_tax_rules.py -q`

Expected: collection fails because `fined.tax_rules` does not exist.

- [ ] **Step 3: Implement the immutable rule model and registry**

Use this public shape:

```python
@dataclass(frozen=True)
class TaxRule:
    rule_id: str
    topic: str
    investment_category: str
    keywords: Sequence[str]
    plain_explanation: str
    effective_from: date
    effective_to: date | None
    applicability_note: str
    official_source_title: str
    official_source_url: str
    last_verified_on: date
    review_due_on: date
    status: Literal["current", "superseded"]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "topic": self.topic,
            "investment_category": self.investment_category,
            "plain_explanation": self.plain_explanation,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": (
                self.effective_to.isoformat() if self.effective_to else None
            ),
            "applicability_note": self.applicability_note,
            "official_source_title": self.official_source_title,
            "official_source_url": self.official_source_url,
            "last_verified_on": self.last_verified_on.isoformat(),
            "review_due_on": self.review_due_on.isoformat(),
            "source_link": (
                f"[{self.official_source_title}]({self.official_source_url})"
            ),
        }
```

The loader accepts exactly the JSON keys above. It bounds every text field, allows only reviewed official hosts and rejects rules whose review date has passed at search time. Token matching is case-folded, deterministic and based only on stored keywords. It never calls the network.

- [ ] **Step 4: Add the verified 2026 rule data**

Include these bounded rules with `last_verified_on: 2026-08-14` and `review_due_on: 2026-09-14`:

1. Tax-year transition from the 1961 Act to the 2025 Act on 1 April 2026.
2. Section 196: 20% STCG for STT-paid equity shares, equity-oriented funds and business trusts.
3. Section 198: 12.5% LTCG on aggregate covered gains above ₹1,25,000 with STT conditions.
4. Equity-oriented fund classification, so TaxEd never calls every ETF an equity ETF.
5. Section 197: 12.5% general LTCG rule without indexation, subject to asset-specific exceptions.
6. Section 76: specified debt mutual funds, MLDs and unlisted bonds treated as short-term in its stated cases.
7. Section 69: buy-back consideration less acquisition cost is capital gain from 1 April 2026, with a warning that promoter additions need professional review.
8. Resident share and mutual-fund dividends are generally taxed at applicable rates, with the official 20% interest-deduction ceiling and no other deduction.
9. Physical gold and covered jewellery GST is 3% of the relevant transaction value. The rule explicitly excludes gold ETFs and sovereign gold bonds.
10. Finance Act 2026 STT rates from 1 April 2026: option sale 0.15%, exercised option 0.15% for purchaser and futures sale 0.05% for seller.
11. Listed bond long-term treatment and the unlisted-bond Section 76 boundary.

Use only the official Income Tax Department Act PDF and transition FAQ, CBIC GST schedule and NSE STT page listed in the design specification.

- [ ] **Step 5: Package data and verify GREEN**

Change package data to:

```toml
[tool.setuptools.package-data]
"fined.data" = ["angel_one_schedules.json", "indian_investment_tax_rules.json"]
```

Run:

```bash
cd backend
uv run pytest tests/test_tax_rules.py -q
uv run ruff check src/fined/tax_rules.py tests/test_tax_rules.py
uv run ruff format --check src/fined/tax_rules.py tests/test_tax_rules.py
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/pyproject.toml backend/src/fined/tax_rules.py backend/src/fined/data/indian_investment_tax_rules.json backend/tests/test_tax_rules.py
git commit -m "feat: add verified Indian investment tax registry"
```

### Task 2: Fresh Consent and Private Context Transfer

**Files:**
- Create: `backend/src/fined/handoff.py`
- Test: `backend/tests/test_handoff.py`

**Interfaces:**
- Produces: `TaxLocale`, `PendingHandoff`, `HandoffDirection`, `TaxRoute`, `normalize_tax_locale()`, `classify_tax_route()`, `permission_prompt()`, `create_pending_handoff()`, `validate_fresh_consent()`, `sanitize_handoff_text()` and `build_handoff_chat_context()`.
- Task 3 stores `PendingHandoff | None` in `SessionState` and calls the validation and context helpers.

- [ ] **Step 1: Write failing consent tests**

Create table-driven tests for exact English, Hindi and Hinglish affirmations. Verify `yes`, `yes please`, `हाँ`, `जी हाँ`, `कर दीजिए`, `haan`, `haan ji` and `ji haan` pass only when they directly follow the exact permission prompt. Verify no, silence, `yes but do not connect`, `I said yes earlier`, an unrelated yes, an intervening assistant question, expiry and replay fail.

Add a context test whose source context contains system instructions, tool calls, an OTP, PAN, email and phone number. The copied context must contain the bounded original tax question but none of the private values or non-conversational items.

Add a literal routing matrix for `classify_tax_route()`. General ETF education, SIP education, paper trading and a live-price request return `fined`. Indian investment capital-gain, dividend, gold GST, bond tax, STT and equity ETF tax questions return `offer_taxed`. Personal ITR filing, personal liability and tax-evasion requests return `refuse`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd backend && uv run pytest tests/test_handoff.py -q`

Expected: collection fails because `fined.handoff` does not exist.

- [ ] **Step 3: Implement exact state and locale contracts**

Use:

```python
TaxLocale = Literal["en-IN", "hi-IN", "hi-LATN"]
HandoffDirection = Literal["taxed", "fined"]
TaxRoute = Literal["fined", "offer_taxed", "refuse"]

@dataclass(frozen=True)
class PendingHandoff:
    offer_id: str
    direction: HandoffDirection
    question: str
    question_fingerprint: str
    locale: TaxLocale
    question_turn_id: str
    permission_text: str
    offered_at: float
    expires_at: float
```

Generate 128-bit offer IDs with `secrets.token_hex(16)`. Hash sanitized UTF-8 question text with SHA-256. The confirmation helper filters `ChatContext.items` to `ChatMessage` objects, finds the stored question turn then requires exactly the fixed assistant permission message followed by the latest user affirmation.

`classify_tax_route()` uses bounded normalized text and fixed investment-tax intent terms. It is a guard on `offer_tax_handoff`, so a model cannot transfer general education or prohibited personal tax work to TaxEd.

- [ ] **Step 4: Implement deterministic privacy filtering and bounded context**

Reject or redact PAN-like strings, email addresses, labelled secrets and digit runs consistent with phone or account numbers. Copy at most six user or assistant messages and 6,000 characters. Build a fresh `llm.ChatContext.empty()` and never copy instructions, function calls or function output.

- [ ] **Step 5: Verify GREEN and commit Task 2**

Run:

```bash
cd backend
uv run pytest tests/test_handoff.py -q
uv run ruff check src/fined/handoff.py tests/test_handoff.py
uv run ruff format --check src/fined/handoff.py tests/test_handoff.py
```

Then:

```bash
git add backend/src/fined/handoff.py backend/tests/test_handoff.py
git commit -m "feat: add fresh agent handoff consent"
```

### Task 3: TaxEd and FinEd Native Agent Handoffs

**Files:**
- Create: `backend/src/fined/taxed_agent.py`
- Create: `backend/src/fined/agent_status_bridge.py`
- Create: `backend/tests/test_taxed_agent.py`
- Create: `backend/tests/test_agent_status_bridge.py`
- Modify: `backend/src/fined/agent.py`
- Modify: `backend/tests/test_agent_contract.py`

**Interfaces:**
- Consumes: `TaxRuleRegistry` from Task 1 and consent/context helpers from Task 2.
- Produces: `TaxEdAssistant`, `build_taxed_prompt()`, `AgentStatus`, `AgentStatusBridge`, `LiveKitAgentStatusBridge` and `AGENT_STATUS_RPC_METHOD = "fined.agent.v1.status"`.
- `TaxEdFactory` is `Callable[[TaxLocale, llm.ChatContext], Agent]`. `FinEdFactory` is `Callable[[llm.ChatContext, bool], Agent]`, where the boolean requests a returning FinEd introduction.
- `SessionState.active_agent_name` is the fixed literal `fined` or `taxed`. `SessionState.agent_handoff_count` increments only after an actual committed change between those agents.
- FinEd tool signatures: `offer_tax_handoff(context, language) -> dict[str, object]` and `handoff_to_taxed(context) -> Agent`.
- TaxEd tool signatures: `search_tax_rules(context, query, as_of_date, category) -> dict[str, object]`, `offer_fined_return(context, language) -> dict[str, object]` and `handoff_to_fined(context) -> Agent`.

- [ ] **Step 1: Write failing specialist-boundary tests**

Prove TaxEd exposes only the three specialist tool contracts. Prove its prompt requires official lookup before every substantive rule, an applicability date, a Markdown source link and abstention when unverified. Verify it refuses personal liability, ITR filing, evasion, tax-saving recommendations and every paper or real order request before provider inference.

Verify a successful lookup returns a public registry record and sets `state.analytics_success_condition == "tax_rule_delivered"`. Verify no result returns `verified: false` and does not mark success.

- [ ] **Step 2: Write failing handoff behavior tests**

Construct a FinEd agent with a fake `TaxEdFactory`, pass an initial `ChatContext` containing the tax question, call `offer_tax_handoff` and assert no agent is created. Add the fixed assistant permission and fresh yes, call `handoff_to_taxed` and assert exactly one agent is returned with the original sanitized question. Replay must fail.

Mirror the test for TaxEd returning to FinEd. Assert TaxEd cannot hand off without a fresh return offer and affirmative response.

Add bridge tests for exact FinEd and TaxEd payloads, participant-scoped destination identity, five-second timeout, maximum payload bytes, strict acknowledgement and fixed public failure. No phone number, question or transcript may enter the payload.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && uv run pytest tests/test_taxed_agent.py tests/test_agent_status_bridge.py tests/test_agent_contract.py -q`

Expected: new tests fail because TaxEd, handoff tools and the agent-status bridge do not exist.

- [ ] **Step 4: Implement TaxEd as a separate `Agent`**

The constructor accepts `registry`, `fined_factory`, `status_bridge`, optional `chat_ctx` and required per-agent `tts`. Call `Agent.__init__` with only TaxEd instructions, that chat context and the Anusha TTS. Reuse `strip_markdown_links_for_speech()` in `tts_node`.

The lookup tool parses strict ISO dates, defaults a current question to the injected clock date and returns at most four registry records. It catches internal errors and returns one fixed unavailable message without source paths or raw exceptions.

Implement `LiveKitAgentStatusBridge.async publish(status)` with exact payload combinations and the acknowledgement `{"version":1,"accepted":true}`. Provide a no-op unavailable publisher for tests and for sessions where browser RPC is not allowed.

- [ ] **Step 5: Add FinEd routing and two-stage tools**

Extend `SessionState` with `pending_handoff: PendingHandoff | None`. Add `taxed_factory` and optional `chat_ctx` to `FinEdAssistant.__init__`. The offer captures the latest user message from `self.chat_ctx` rather than trusting model-supplied question text. The confirm tool validates the stored offer, speaks a localized connecting sentence through `context.session.say()` and returns the factory-created TaxEd agent.

Set `state.active_agent_name` in each receiving agent's `on_enter` path before its first speech. Increment `state.agent_handoff_count` only when the prior fixed agent name differs and the receiving agent has actually entered. Initial FinEd activation does not count as a handoff. This state is the only attribution source for Task 6 speaking-time analytics.

Update FinEd instructions so general ETF education stays with FinEd while Indian investment-tax intent must use the consent tools. Tax tools are unavailable in outbound reminder sessions.

TaxEd's `on_enter` speaks a brief localized introduction then publishes the active status. FinEd's returning instance does the same with Nikhil. A status-publish failure is swallowed after safe logging. A factory or return failure raises fixed `ToolError` copy and leaves the originating agent active so the user can retry.

- [ ] **Step 6: Verify GREEN and commit Task 3**

Run:

```bash
cd backend
uv run pytest tests/test_taxed_agent.py tests/test_handoff.py tests/test_agent_contract.py -q
uv run pytest tests/test_agent_status_bridge.py -q
uv run ruff check src/fined/agent.py src/fined/taxed_agent.py src/fined/agent_status_bridge.py tests/test_taxed_agent.py tests/test_agent_status_bridge.py tests/test_agent_contract.py
uv run ruff format --check src/fined/agent.py src/fined/taxed_agent.py src/fined/agent_status_bridge.py tests/test_taxed_agent.py tests/test_agent_status_bridge.py tests/test_agent_contract.py
```

Then:

```bash
git add backend/src/fined/agent.py backend/src/fined/taxed_agent.py backend/src/fined/agent_status_bridge.py backend/tests/test_agent_contract.py backend/tests/test_taxed_agent.py backend/tests/test_agent_status_bridge.py
git commit -m "feat: add consented TaxEd agent handoff"
```

### Task 4: LiveKit Wiring and Anusha Voice

**Files:**
- Modify: `backend/src/agent.py`
- Modify: `backend/tests/test_entrypoint_lifecycle.py`

**Interfaces:**
- Consumes: `TaxRuleRegistry`, `TaxEdAssistant` and `LiveKitAgentStatusBridge` from Tasks 1 and 3.
- Produces: one browser-only recursive FinEd and TaxEd factory pair bound to the current LiveKit job.

- [ ] **Step 1: Write failing lifecycle tests**

Extend the entrypoint fake Murf constructor to record every instance. Assert the session default remains:

```python
{"voice": "Nikhil", "style": "Conversational", "model": "falcon-2", "locale": "en-IN"}
```

Invoke the captured TaxEd factory for each supported locale and assert it creates `en-IN-anusha` with the requested locale, `Conversational`, `falcon-2`, the existing sentence tokenizer and text pacing. Assert unknown locale becomes `en-IN`. Assert browser sessions receive a real status bridge while outbound reminder sessions cannot create TaxEd.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && uv run pytest tests/test_entrypoint_lifecycle.py -q`

Expected: tests fail because registry, bridge and factory wiring are absent from the entrypoint.

- [ ] **Step 3: Implement the recursive factories**

In `my_agent`, load the packaged registry once per job. Create these closures:

```python
def create_fined(chat_ctx=None, announce_entry=False) -> FinEdAssistant:
    return FinEdAssistant(
        profile,
        chat_ctx=chat_ctx,
        taxed_factory=create_taxed,
        status_bridge=status_bridge,
        announce_entry=announce_entry,
    )

def create_taxed(locale, chat_ctx) -> TaxEdAssistant:
    return TaxEdAssistant(
        registry=tax_registry,
        chat_ctx=chat_ctx,
        fined_factory=create_fined,
        status_bridge=status_bridge,
        tts=murf.TTS(
            voice="en-IN-anusha",
            style="Conversational",
            model="falcon-2",
            locale=normalize_tax_locale(locale),
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
    )
```

`create_taxed` constructs a per-agent `murf.TTS` with Anusha. `create_fined` relies on the session-level Nikhil TTS. Both receive the same status bridge and factory closures. Start the session with `create_fined()`.

If registry loading fails, log only the fixed registry-unavailable warning and start FinEd with no TaxEd factory. Outbound sessions always receive no TaxEd factory even when the registry is healthy.

- [ ] **Step 4: Verify GREEN and commit Task 4**

Run:

```bash
cd backend
uv run pytest tests/test_entrypoint_lifecycle.py tests/test_taxed_agent.py tests/test_agent_status_bridge.py -q
uv run ruff check src/agent.py tests/test_entrypoint_lifecycle.py
uv run ruff format --check src/agent.py tests/test_entrypoint_lifecycle.py
```

Then:

```bash
git add backend/src/agent.py backend/tests/test_entrypoint_lifecycle.py
git commit -m "feat: wire Anusha specialist into LiveKit"
```

### Task 5: Strict Frontend Agent Status and Accessible Badge

**Files:**
- Create: `frontend/lib/agent-handoff.ts`
- Create: `frontend/components/agent-handoff/agent-handoff-provider.tsx`
- Create: `frontend/components/agent-handoff/active-agent-badge.tsx`
- Create: `frontend/tests/agent-handoff-rpc.test.mjs`
- Create: `frontend/tests/agent-handoff-integration.test.mjs`
- Modify: `frontend/components/app/app.tsx`
- Modify: `frontend/components/app/fin-ed-session-view.tsx`
- Modify: `frontend/tests/view-controller.test.mjs`

**Interfaces:**
- Produces: `ActiveAgentStatus`, `decodeActiveAgentStatus()`, `createAgentStatusRpcHandler()`, `AgentHandoffProvider`, `useAgentHandoff()` and `ActiveAgentBadge`.
- Context value is `{ activeAgent: ActiveAgentStatus }` and defaults to the fixed FinEd status.

- [ ] **Step 1: Write failing decoder and authorization tests**

Accept only these exact combinations:

```typescript
{
  version: 1,
  active_agent: 'fined',
  display_name: 'FinEd Saathi',
  voice_name: 'Nikhil',
  specialty: null,
}
```

```typescript
{
  version: 1,
  active_agent: 'taxed',
  display_name: 'TaxEd',
  voice_name: 'Anusha',
  specialty: 'Investment Tax Specialist',
}
```

Reject unknown keys, mixed identity combinations, invalid versions, oversized UTF-8 payloads and callers other than the connected backend agent. Assert the acknowledgement is exactly `{"version":1,"accepted":true}`.

- [ ] **Step 2: Write failing provider and UI tests**

Verify the provider registers and unregisters `fined.agent.v1.status`, resets to FinEd when the connected agent participant changes and ignores registration errors. Render the session view and assert it initially shows FinEd with Nikhil then shows TaxEd with Anusha and `Investment Tax Specialist` after a valid handler call. The badge must use `role="status"`, `aria-live="polite"` and no forced animation.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
cd frontend
node --test tests/agent-handoff-rpc.test.mjs tests/agent-handoff-integration.test.mjs tests/view-controller.test.mjs
```

Expected: new modules are missing or new assertions fail.

- [ ] **Step 4: Implement the strict decoder, provider and badge**

Keep the decoder in the framework-independent library. Register the RPC in a React effect only when `useAgent()` exposes a connected participant identity. Use a stable callback and clean up the exact registered method.

Mount `AgentHandoffProvider` inside `AgentSessionProvider` and outside the workspace providers. Replace hard-coded live header identity and voice text with the validated context. Do not unmount the transcript, session list or paper dashboard when status changes.

- [ ] **Step 5: Verify GREEN and commit Task 5**

Run:

```bash
cd frontend
node --test tests/agent-handoff-rpc.test.mjs tests/agent-handoff-integration.test.mjs tests/view-controller.test.mjs
pnpm exec tsc --noEmit
pnpm exec prettier --check lib/agent-handoff.ts components/agent-handoff components/app/app.tsx components/app/fin-ed-session-view.tsx tests/agent-handoff-rpc.test.mjs tests/agent-handoff-integration.test.mjs tests/view-controller.test.mjs
```

Then:

```bash
git add frontend/lib/agent-handoff.ts frontend/components/agent-handoff frontend/components/app/app.tsx frontend/components/app/fin-ed-session-view.tsx frontend/tests/agent-handoff-rpc.test.mjs frontend/tests/agent-handoff-integration.test.mjs frontend/tests/view-controller.test.mjs
git commit -m "feat: show active voice specialist"
```

### Task 6: Analytics, Documentation and Full Verification

**Files:**
- Modify: `backend/src/fined/call_analytics.py`
- Modify: `backend/src/agent.py`
- Modify: `backend/tests/test_call_analytics.py`
- Modify: `backend/tests/test_entrypoint_lifecycle.py`
- Modify: `frontend/lib/call-analytics.ts`
- Modify: `frontend/components/analytics/call-analytics-dashboard.tsx`
- Modify: `frontend/tests/call-analytics.test.mjs`
- Modify: `README.md`
- Modify: `backend/README.md`

**Interfaces:**
- Adds `tax_rule_delivered` to the existing analytics success allowlist and rank.
- Records privacy-safe agent speaking duration for FinEd and TaxEd plus the handoff count for each call.
- Publishes per-call and aggregate agent speaking time without caller identity, transcripts or utterance text.
- Adds the Day 9 manual test and demonstration script to human documentation.

- [ ] **Step 1: Write failing analytics tests**

Add `tax_rule_delivered` as a literal accepted analytics success with no stored question or amount. Assert the public summary stores only the fixed condition string and never stores a question, asset, amount or source URL. The routing matrix is already covered against the production `classify_tax_route()` guard in Task 2 and against the FinEd offer tool in Task 3.

Add RED tests for a privacy-safe `AgentTalkTimeTracker`. It must consume `agent_state_changed` speaking intervals using an injected monotonic clock, attribute each completed interval to the active `fined` or `taxed` agent and close an open interval during shutdown. Unknown agent labels and duplicate state transitions fail closed. A switch from FinEd to TaxEd increments one handoff. The public record and summary expose integer `fined_talk_seconds`, `taxed_talk_seconds` and `handoff_count` only. Their sum may not exceed total call duration by more than one rounding second.

Add frontend decoder and dashboard RED tests for summary version 2. The totals show aggregate FinEd and TaxEd speaking time. Each recent call shows total duration, FinEd time, TaxEd time and handoff count. Reject extra keys, negative values, fractional values, impossible sums and caller or transcript fields.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && uv run pytest tests/test_call_analytics.py -q`

Expected: `tax_rule_delivered` is rejected by the current allowlist and the new speaking-time fields do not exist.

- [ ] **Step 3: Implement analytics and operator documentation**

Add `tax_rule_delivered` below `grounded_answer_delivered` in the success ranking so a later completed paper fill still wins. Update `CALL_SUCCESS_DEFINITION` to include a verified tax rule.

Register one `agent_state_changed` listener in the LiveKit entrypoint. On each transition to speaking, capture `state.active_agent_name` and the monotonic start. On each transition away from speaking, close that interval. Close any remaining interval before analytics persistence at shutdown. Task 3 must set `state.active_agent_name` to `fined` or `taxed` in each agent's `on_enter` path and increment `state.agent_handoff_count` only after a committed agent change. Never infer identity from transcript text, voice names or provider labels.

Migrate the analytics table additively and keep old rows readable as zero speaking time and zero handoffs. Publish summary version 2 with aggregate and recent-call `fined_talk_seconds`, `taxed_talk_seconds` and `handoff_count`. Update the strict frontend decoder and the responsive analytics table to show the breakdown. User-facing labels are `FinEd speaking`, `TaxEd speaking` and `Handoffs`.

Document:

- TaxEd scope and Anusha voice
- current-law verification date of 2026-08-14
- Income-tax Act, 2025 transition boundary
- English, Hindi and Hinglish handoff prompts
- the explicit permission requirement
- the normal FinEd route and TaxEd route demo questions
- the fact that TaxEd cannot trade, calculate personal liability or file an ITR
- how to refresh registry verification dates only after checking official sources
- how the dashboard measures FinEd and TaxEd speaking time without storing audio or transcripts

- [ ] **Step 4: Run the complete backend verification**

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Expected: all commands exit 0 with no failures.

- [ ] **Step 5: Run the complete frontend verification**

```bash
cd frontend
node --test tests/*.test.mjs
pnpm exec tsc --noEmit
pnpm format:check
pnpm build
```

Expected: all tests pass, TypeScript exits 0, formatting passes and Next.js produces all routes.

- [ ] **Step 6: Verify source and repository hygiene**

```bash
git diff --check
git status --short
git log --oneline --decorate -8
```

Confirm `.env`, generated databases, logs and local knowledge indexes are not staged. Confirm the only unpushed commits are intentional project commits.

- [ ] **Step 7: Commit Task 6**

```bash
git add README.md backend/README.md backend/src/agent.py backend/src/fined/call_analytics.py backend/tests/test_call_analytics.py backend/tests/test_entrypoint_lifecycle.py frontend/lib/call-analytics.ts frontend/components/analytics/call-analytics-dashboard.tsx frontend/tests/call-analytics.test.mjs
git commit -m "docs: finish Day 9 TaxEd handoff"
```

- [ ] **Step 8: Re-run final evidence after the last commit**

Run the full backend and frontend commands from Steps 4 and 5 again, then run `git status --short --branch`. Completion requires a clean worktree.
