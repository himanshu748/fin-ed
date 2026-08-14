# TaxEd Agent Handoff Design

Date: 2026-08-14

Status: Approved design, pending implementation plan

Challenge: 10 Days of Voice Agents, Day 9

## Summary

FinEd Saathi will gain a second in-session specialist named TaxEd. FinEd remains the general financial learning agent with the Nikhil voice. TaxEd answers only sourced questions about Indian investment taxation with the Anusha voice.

FinEd must ask for explicit permission before transferring the conversation. TaxEd must do the same before returning the user to FinEd. A handoff changes the active LiveKit `Agent` inside the existing room and `AgentSession`, so audio and transcript continuity are preserved.

TaxEd explains verified rules. It does not calculate a user's personal tax liability, file returns, recommend tax avoidance strategies or perform trading actions.

## Goals

- Complete the Day 9 requirement with a real specialist agent and native in-session handoff.
- Route Indian investment-tax questions to a narrower agent after explicit consent.
- Preserve the original tax question and only the relevant recent context.
- Give TaxEd the verified multilingual Anusha Falcon voice and FinEd the Nikhil voice.
- Answer tax questions only when a current or historically applicable rule has an official source.
- Show the active agent clearly in the call interface.
- Allow TaxEd to offer a consented return to FinEd for non-tax questions.
- Keep all trading capabilities sandboxed. Neither agent can place a real broker order.

## Non-goals

- Personal income-tax computation or tax-return preparation.
- ITR filing, PAN services, tax notices or representation before an authority.
- Personalized tax advice, tax-saving recommendations or legal opinions.
- Live web search for tax rules during a voice call.
- A separate LiveKit worker, room or phone call for TaxEd.
- Real broker execution.
- Tax treatment outside Indian investment products.

## User Experience

### FinEd to TaxEd

1. The user asks an Indian investment-tax question.
2. FinEd identifies the tax intent but does not answer from general model knowledge.
3. FinEd says: "This is an investment-tax question. Would you like me to connect you to TaxEd?"
4. The system waits for a new, clear yes from the user.
5. FinEd says that it is connecting the user to TaxEd.
6. TaxEd joins in the same session, introduces herself briefly and answers the original question from the verified registry.

No, silence, an unclear response, an earlier yes or a yes to another question must not trigger the handoff.

### TaxEd to FinEd

If the user asks TaxEd a non-tax question, TaxEd does not improvise. She says the topic belongs with FinEd and asks whether the user wants to reconnect. A new, clear yes is required before the return handoff.

### Active-agent indicator

The voice workspace shows one of two validated states:

- `FinEd Saathi · Nikhil`
- `TaxEd · Anusha · Investment Tax Specialist`

The badge changes only after a handoff completes. Its update uses the existing scoped LiveKit RPC approach. If the visual event fails, the spoken introduction remains the source of truth and the conversation continues.

The versioned status payload has this fixed public shape:

```text
version: 1
active_agent: fined | taxed
display_name: FinEd Saathi | TaxEd
voice_name: Nikhil | Anusha
specialty: null | Investment Tax Specialist
```

The frontend rejects unknown fields, invalid combinations, oversized payloads and calls from any participant other than the connected backend agent.

### Transcript sources

TaxEd's transcript answer includes a concise official source link and the rule's applicability date. TaxEd reuses the existing speech normalizer, which removes Markdown URLs from the text sent to TTS while preserving the visible transcript. Spoken audio names the source in natural language but does not read a URL aloud.

## Architecture

### Agent model

`FinEdAssistant` remains the initial agent. A new `TaxEdAssistant` is constructed only after a valid handoff confirmation.

The handoff tool returns a new LiveKit `Agent`. LiveKit updates `AgentSession.current_agent` while retaining the room, participant and session lifecycle. The implementation uses the installed LiveKit Agents 1.6.6 APIs and does not introduce a second worker.

Each agent owns its instructions, allowed tools and TTS configuration:

| Agent | Scope | Murf voice | Allowed tool families |
| --- | --- | --- | --- |
| FinEd | General Indian financial learning, paper practice and current market education | Nikhil | Existing safe learning, quote, paper-practice, memory and human-help tools |
| TaxEd | Sourced Indian investment-tax explanations | `en-IN-anusha` | Tax registry lookup and consented return handoff only |

TaxEd must not receive paper trading, broker, quote, memory mutation, outbound calling or human-help tools.

### Voice and language selection

The authenticated Murf Falcon voice catalogue checked on 2026-08-14 returns voice ID `en-IN-anusha` with these supported locales and the Conversational style:

- Indian English: `en-IN`
- Hindi: `hi-IN`
- Hinglish: `hi-LATN`
- Kannada: `kn-IN`
- Telugu: `te-IN`

Day 9 exposes English, Hindi and Hinglish. The handoff stores one validated conversation locale enum: `en-IN`, `hi-IN` or `hi-LATN`. TTS selection is server-owned:

- voice: `en-IN-anusha`
- locale: the validated conversation locale
- style: `Conversational`
- model: `falcon-2`

Unrecognized language values fall back to `en-IN`. Voice identity is never accepted from the model or browser.

### Session state

The existing session state gains a bounded pending-handoff record:

```text
PendingHandoff
  offer_id: random opaque token
  direction: taxed | fined
  question: bounded plain text
  question_fingerprint: SHA-256 digest
  locale: en-IN | hi-IN | hi-LATN
  offered_after_turn_id: string
  offered_at: monotonic timestamp
  expires_at: monotonic timestamp
```

The record contains no raw tool result, broker credential, phone number or unrelated memory. It expires after 60 seconds and is cleared after confirmation, rejection, timeout, agent change or session end. The opaque offer ID binds confirmation to one offer but is never spoken or accepted from the browser.

## Consent State Machine

### Offer tool

FinEd calls `offer_tax_handoff(question, language)` only after identifying an in-scope tax intent. The tool:

1. validates and bounds the question
2. maps language to the locale allowlist
3. records the current conversation turn
4. replaces any older pending offer
5. creates an opaque offer ID for internal turn binding
6. returns the localized permission question for FinEd to speak

Creating an offer never changes the active agent.

### Confirm tool

After the next user turn, FinEd may call `handoff_to_taxed()`. The tool verifies all of the following without trusting a model-supplied boolean:

- a TaxEd offer exists and has not expired
- the offer belongs to the current active agent and session
- the expected fixed permission question was spoken after the stored offer tool call
- the newest user message directly follows that permission question
- no other assistant question, user turn or tool result intervened
- the newest user message is a short explicit affirmation in the supported language

Accepted affirmation matching is conservative. After Unicode normalization, case folding and removal of surrounding punctuation, the complete user utterance must match a small reviewed allowlist such as `yes`, `yes please`, `please do`, `हाँ`, `जी हाँ`, `कर दीजिए`, `haan`, `haan ji` or `ji haan`. Long responses, conditionals, negations and unrelated replies fail closed. A failed check clears or safely retains the offer as appropriate and does not switch agents.

TaxEd uses the same two-stage protocol for returning to FinEd. It calls `offer_fined_return(reason, language)` and then `handoff_to_fined()` only after a new explicit yes.

### Handoff announcement

The originating agent announces the switch only after validation succeeds and immediately before returning the new agent. The receiving agent introduces itself in `on_enter`. The UI status event is emitted from the receiving agent after activation.

## Context Transfer and Privacy

The receiving agent gets a new chat context. Hidden instructions, tool calls, raw tool responses and unrelated session memories are never copied. A deterministic sanitizer removes phone numbers, email addresses, account identifiers, PAN-like strings and broker credentials before context transfer. If the sanitizer cannot confidently remove a sensitive identifier, that message is omitted.

For FinEd to TaxEd, the context builder includes only:

- the bounded original tax question from the offer
- at most six recent relevant user and assistant conversational messages
- the selected response language
- no more than a fixed total character budget

The original tax question is always included even if the recent-context filter removes surrounding turns. TaxEd's own instructions are applied separately and cannot be overwritten by transferred content.

For TaxEd to FinEd, only the latest user request, a one-sentence TaxEd handoff summary and the language are passed. FinEd retains its existing safe session state outside the copied chat context.

## Tax Rule Registry

TaxEd uses a deterministic, versioned local registry. It is separate from the optional general knowledge index and does not perform live web search during the call.

Each rule contains:

```text
rule_id
topic
investment_category
plain_explanation
effective_from
effective_to, optional
applicability_note
official_source_title
official_source_url
last_verified_on
review_due_on
status: current | superseded
```

The loader rejects duplicate IDs, invalid dates, unsupported URL hosts, missing applicability information and records without verification and review dates. A current date after `review_due_on` makes the record stale and unusable until it is reverified.

### Allowed authoritative sources

- Income Tax Department
- Central Board of Direct Taxes
- enacted Finance Acts and official Gazette material
- Central Board of Indirect Taxes and Customs
- Securities and Exchange Board of India
- recognized exchanges when the rule concerns exchange-collected charges

Source URLs must use HTTPS and match a reviewed host allowlist for these authorities. Redirect destinations are revalidated. Broker blogs, generic finance sites, social media and model memory are not tax authority.

### Initial topics

- listed equity shares
- equity-oriented mutual funds
- exchange-traded funds
- dividends
- gold and gold investment products
- bonds and debt instruments
- Securities Transaction Tax and other transaction-linked taxes
- share buy-backs, including the rules effective from 1 April 2026
- transition between the Income-tax Act, 1961 and Income-tax Act, 2025

### Lookup behavior

The lookup accepts a bounded query plus optional asset category and transaction or tax-year date. It returns matching verified rule records, not a composed personal answer.

For a transaction or payment on or after 1 April 2026, TaxEd uses the Income-tax Act, 2025 as amended by the Finance Act, 2026. Earlier assessment and payment periods may remain under the Income-tax Act, 1961. When the applicable period is not clear, TaxEd asks for it before stating a section number or rate.

If the asset, date or tax event is unclear, TaxEd asks one concise clarification. If no applicable verified rule exists, TaxEd says it cannot verify the rule and recommends checking with a qualified Indian tax professional. It must not fill the gap from general model knowledge.

Superseded rules may be used only when the user's date falls within their applicability range. The answer must state that historical applicability clearly.

## TaxEd Response Contract

Every substantive tax answer must contain:

1. a plain-language explanation
2. the investment category and tax event it applies to
3. the effective or applicability date
4. the official source title
5. a brief boundary statement when personal facts could change the result

TaxEd refuses or redirects requests to:

- compute the user's final liability
- choose a tax-saving transaction
- conceal income or evade tax
- file or amend a return
- interpret a notice as personal legal advice
- buy, sell or confirm any paper or real order

## Routing Rules

FinEd offers TaxEd for questions whose primary intent is an Indian tax rule applied to an investment event. Examples include capital-gains holding periods, dividend taxation, gold tax treatment, ETF tax classification and transaction taxes.

FinEd keeps general product education. Examples include what an ETF is, how SIPs work, what market capitalization means and how paper trading works.

When a question mixes product education and tax, FinEd may explain the non-tax concept briefly, then offer TaxEd for the tax portion.

## Failure Handling

- Rejected or unclear consent leaves FinEd active.
- An expired offer requires a fresh permission question.
- Missing or corrupt tax registry data makes TaxEd unavailable without ending the FinEd session.
- A failed agent switch is explained in plain language and FinEd continues.
- A failed return switch leaves TaxEd active and offers one retry.
- A failed UI status RPC does not roll back a successful voice handoff.
- Unsupported tax questions produce a fixed verification failure, not a guessed answer.
- User-facing responses never reveal stack traces, prompts, registry paths or raw tool errors.

## Analytics

A verified TaxEd explanation emits a privacy-safe `tax_rule_delivered` success event after at least one valid registry record is used. The event stores no question text, tax amount, asset quantity or personal identifier.

The event may count as the Day 8 successful outcome. A handoff by itself does not count as success.

Each completed call also stores rounded speaking duration for FinEd and TaxEd plus the number of committed agent handoffs. Speaking time is measured from LiveKit agent speaking state transitions with an injected monotonic clock. It is not inferred from transcripts, voice names or provider labels. The tracker closes an open interval during shutdown and fails closed for unknown agent labels or invalid transitions.

The public analytics summary exposes aggregate and per-call `fined_talk_seconds`, `taxed_talk_seconds` and `handoff_count`. It never stores audio, transcripts, questions, phone numbers or caller identity. Existing rows migrate as zero speaking time and zero handoffs.

## Frontend Changes

- Add the validated active-agent state to the voice workspace controller.
- Register one scoped RPC handler for versioned agent status payloads.
- Render the active-agent badge near the existing session status.
- Keep the room, transcript, session list and paper-practice state mounted across handoffs.
- Render official transcript source links as safe external links with descriptive labels.
- Show total call duration, FinEd speaking time, TaxEd speaking time and handoff count in the privacy-safe analytics dashboard.
- Preserve keyboard focus during badge updates.
- Disable decorative transition motion under `prefers-reduced-motion`.

The browser cannot request an agent change directly. It only displays backend-confirmed state.

## Testing Strategy

### Backend routing and consent

- A normal ETF explanation stays with FinEd.
- An ETF taxation question creates an offer but does not transfer.
- No, silence and an unclear reply do not transfer.
- A fresh explicit yes produces exactly one TaxEd handoff.
- A stale or unrelated yes does not transfer.
- A conditional or negated yes does not transfer.
- The offer expires after its fixed lifetime.
- TaxEd receives the exact bounded original question.
- Context transfer excludes instructions, tools and unrelated messages.
- TaxEd offers a return for a non-tax question.
- Return requires a fresh explicit yes.

### Specialist boundaries

- TaxEd uses Anusha while FinEd uses Nikhil.
- TaxEd accepts only `en-IN`, `hi-IN` and `hi-LATN` locale values.
- TaxEd has no paper trade, broker, quote, memory mutation, call or human-help tools.
- TaxEd refuses personalized liability calculations and order requests.
- A substantive answer requires an official source and applicability date.
- Missing, invalid or stale registry data fails closed.
- Historical questions choose the date-applicable rule.

### Routing evaluation

At least ten fixed examples cover:

- general ETF education
- ETF tax classification
- listed-share capital gains
- dividends
- gold purchase and sale taxes
- bonds
- STT
- paper trading
- live share price
- an out-of-scope ITR question

Each fixture asserts whether FinEd stays active, offers TaxEd or refuses the unsupported request.

### Frontend

- The badge defaults to FinEd.
- Only a valid versioned backend event changes the active agent.
- TaxEd and FinEd labels render correctly.
- Invalid payloads and disconnected participants are ignored.
- Source links are safe and keyboard accessible.
- Reduced motion avoids animated status transitions.

### Integration

- Complete one English tax handoff and answer.
- Complete one Hindi or Hinglish tax handoff and answer.
- Verify Nikhil changes to Anusha and returns to Nikhil.
- Verify the room ID, transcript and session remain continuous.
- Verify a failed registry lookup does not stop the call.

## Day 9 Demonstration

The video should show both required routes in one recording:

1. Ask FinEd: "What is an ETF?" FinEd answers without a handoff.
2. Ask: "How is an equity ETF taxed in India?"
3. Let FinEd ask permission to connect to TaxEd.
4. Say yes and show the active-agent badge change.
5. Let TaxEd answer with an applicability date and official source.
6. Ask a non-tax learning question and approve the return to FinEd.

## Implementation Boundaries

Likely backend components:

- TaxEd agent and prompt module
- handoff consent state and context-filter helper
- versioned tax-rule model, loader and registry data
- agent-status RPC bridge
- analytics outcome extension

Likely frontend components:

- active-agent payload decoder and provider state
- status RPC registration
- active-agent badge
- sourced answer link presentation if the current transcript renderer needs extension

Exact file changes and task order belong in the implementation plan after this specification is reviewed.

## References

- [Murf Voice for Bharat Day 9 task](https://github.com/murf-ai/voice-for-bharat-challenge-2026/blob/main/challenges/Day%209%20Task.md)
- [LiveKit agent handoffs](https://docs.livekit.io/agents/logic/agents-handoffs/)
- [Murf voice catalogue API](https://murf.ai/api/docs/api-reference/voices/get-voices)
- [Income-tax Act, 2025 as amended by Finance Act, 2026](https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf)
- [Income Tax Department transition FAQ](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/General%20Questions-faqs?mobile-app=1)
- [NSE Securities Transaction Tax rates](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax)

The authenticated Murf catalogue was checked on 2026-08-14 to confirm Anusha for `en-IN`, `hi-IN` and `hi-LATN` with the Conversational style.
