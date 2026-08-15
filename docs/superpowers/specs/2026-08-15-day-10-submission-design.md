# Day 10 Submission Package Design

**Date:** 2026-08-15
**Status:** Approved for implementation

## Objective

Produce a complete Day 10 submission package for FinEd Saathi that tells a personal story, proves the product through safe visual evidence and helps another builder run the project. The final public repository must stay clean and must not contain an article draft, internal design documents, old implementation plans or duplicate setup guides.

## Required outcomes

1. A publish-ready DEV Community article prepared outside the tracked repository.
2. A root `README.md` that is the canonical setup, configuration, testing and troubleshooting guide.
3. Fresh product screenshots and an architecture diagram stored with the public product assets.
4. A reviewed `RED_TEAM.md` that remains only when its claims are accurate and useful.
5. LinkedIn and X copy for sharing the published article and Day 10 result.
6. A clean main branch pushed to GitHub after tests, builds, privacy checks and link checks pass.

## Article concept

### Working title

**I Bought a ₹6 Share and Learned the Hard Way: Building FinEd Saathi in 10 Days**

### Audience

- Indian first-time investors who want concepts explained without intimidating jargon
- Builders creating safe multilingual voice products for India
- VoiceForBharat reviewers who need to understand the problem, implementation and evidence quickly

### Narrative structure

1. Open with the personal brokerage-charge surprise and the financial-literacy gap it revealed.
2. Explain the user, the problem and why a voice interface improves access.
3. Show how the system works through a compact architecture diagram.
4. Prove the main features with product screenshots instead of presenting a ten-day changelog.
5. Describe the hardest implementation problems honestly.
6. Provide practical setup, testing and troubleshooting guidance.
7. Close with the public repository, the demo outcome and realistic next steps.

### Product positioning

The article will identify Murf Falcon as the fastest TTS API, matching the challenge wording. It will explain that Nikhil powers FinEd Saathi and Anusha powers TaxEd. It will describe their Indian multilingual use without claiming unsupported locales or capabilities.

### Feature evidence

The proof-first section will cover:

- A multilingual FinEd voice conversation
- A consented FinEd to TaxEd handoff and return
- Sourced Indian investment-tax explanations
- Live market quotes with explicit unavailable-data handling
- Paper trading that cannot place real broker orders
- Session memory
- Human help escalation
- Safe outbound call support
- Per-agent call analytics

### Honest challenges

The article will explain:

- Broker authentication and short-lived market-data credentials
- Telephony setup across Twilio and LiveKit
- Reliable browser-independent specialist handoffs
- The need to fail closed when a current quote or sourced tax rule cannot be verified
- Guardrails that keep education and paper trading separate from real trading

## Visual evidence plan

The article will use the approved proof-first sequence:

1. Existing original FinEd artwork as the cover
2. Fresh landing-page screenshot
3. Fresh connected voice-workspace screenshot
4. Fresh TaxEd handoff screenshot that shows Anusha and a source-backed answer
5. Fresh paper-trading dashboard screenshot
6. Fresh call-analytics screenshot
7. Fresh human-help screenshot when it adds evidence and remains privacy-safe

The architecture diagram will show:

`Browser or phone → LiveKit → Deepgram STT → Gemini with guardrails and tools → Murf Falcon TTS`

It will also show browser-owned paper trading, the sourced tax registry, optional Angel One market data, SQLite memory and analytics as side systems.

### Visual privacy rules

- Do not show phone numbers, session IDs, caller identifiers, access tokens or API credentials.
- Do not show personal portfolio data that belongs to a real account.
- Retake a screenshot when cropping cannot safely remove sensitive data.
- Use only original project artwork and real product screens.
- Add useful alt text and keep text readable at article width.

## README consolidation

The root README will become the only setup guide. It will include:

1. Product purpose and safety boundary
2. Architecture and technology stack
3. Prerequisites
4. Environment variables grouped into required and optional features
5. Frontend installation and startup
6. Backend installation and LiveKit agent startup
7. Murf Falcon voice configuration
8. Gemini and Deepgram configuration
9. Optional Angel One live quotes
10. Optional Twilio and LiveKit telephony
11. Local testing commands
12. Common failures and fixes
13. Privacy, paper-trading and real-trade restrictions
14. Public screenshots and challenge attribution

Examples must use placeholders only. No real secret, phone number, broker identifier or private LiveKit value may appear in the tracked files or history introduced by this work.

## Repository cleanup

Useful information will be merged into the root README before removing duplicate or internal Markdown files.

### Keep in the final tracked tree

- `README.md`
- `RED_TEAM.md`, after an accuracy and relevance review

### Remove from the final tracked tree

- `AGENTS.md`
- `backend/README.md`
- `frontend/README.md`
- `docs/DESIGN.md`
- Tracked files under `docs/superpowers/plans/`
- Tracked files under `docs/superpowers/specs/`

This design specification is committed as a required design checkpoint. It will be removed with the other internal specifications during the approved cleanup so the final repository follows the two-document rule. Its reasoning will remain available in Git history.

The DEV article will be prepared in an ignored working file or delivered directly in the final handoff. It must not be committed as `DAY10.md` or under another tracked name.

## Error handling and truthful claims

- Optional integrations must be labelled optional.
- A failed live quote must be described as unavailable rather than replaced with fabricated data.
- A failed tax-rule lookup must abstain and request a narrower question or human review.
- Setup instructions must distinguish required configuration from broker and telephony extensions.
- The article must not imply that the agent can place real trades.
- Claims about voices, models and current tax behavior must match the shipped configuration and sourced rules.

## Verification

Before the final push:

1. Run the deterministic backend test suite and Ruff checks.
2. Run the frontend test suite, TypeScript check, format check and production build.
3. Run focused handoff, TaxEd, paper-trading, analytics and safety tests.
4. Verify every README command against the current package scripts and application entry points.
5. Check all public links.
6. Scan tracked files for secrets, phone numbers, session IDs and private identifiers.
7. Confirm every screenshot is privacy-safe and readable.
8. Confirm tracked Markdown contains only `README.md` and `RED_TEAM.md`.
9. Confirm `git status` is clean.
10. Push the final commit to the public main branch.

## Publication handoff

The final response will provide:

- The finished DEV article in a copy-ready form or an ignored local draft path
- The ordered image list with captions and alt text
- LinkedIn copy that tags Murf AI and includes the required challenge hashtags
- An X thread with the same factual claims
- The verified GitHub repository URL
- A short Day 10 submission checklist
