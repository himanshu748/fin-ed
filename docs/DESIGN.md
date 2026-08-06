# Generated-app design system

Every app the swarm ships follows these rules. The frontend agent receives this file verbatim in its system prompt; the critic may flag high-severity violations of the non-negotiables.

## Non-negotiables

1. Responsive from 360px to 1440px. The head contains exactly `<meta name="viewport" content="width=device-width, initial-scale=1">`. Layout uses flex/grid with sensible wrapping; no horizontal page scroll at any width; touch targets at least 40px.
2. Real interactivity with real states: hover, focus-visible, disabled, loading, empty and error states all designed, not defaulted. An empty screen tells the user what to do next.
3. Accessible floor: semantic elements (button, form, label), contrast at least 4.5:1 for body text, visible keyboard focus, `prefers-reduced-motion` respected.
4. No lorem ipsum, no placeholder images, no dead buttons. If a control exists, it works.

## Look and feel

- Color comes from the subject's world, never from habit. Ask: what would this thing's physical or cultural materials look like? A recipe journal earns warm paper and tomato red, a finance tool earns banknote green or ledger ink blue, a sleep app earns deep night blues, a climbing log earns chalk and granite. Commit to the palette the plan's design_direction names.
- Banned defaults: do not reach for emerald/mint green, teal or violet-on-near-black unless the subject specifically earns them (a forest app earns green; a generic tracker does not). These are the palettes every AI tool produces; producing them means the design failed.
- Dark or light is also a subject decision: night-adjacent and focus subjects go dark; domestic, editorial, health and daytime subjects usually deserve a light or warm theme. Do not default to dark. Same discipline either way: deep neutral surfaces, one saturated accent, neutrals for everything else.
- Type: choose real typefaces on purpose and load them from Google Fonts with a preconnect. Pair a display face that carries the subject's character with a clean text face, and add a mono only where numbers or labels earn it. Editorial and domestic subjects usually want a serif display (Fraunces, Instrument Serif, Newsreader, Lora); technical and utility subjects want a confident sans (Geist, Inter Tight, Space Grotesk). Falling back to the system stack is a failure of nerve, not restraint: it is the single clearest tell of a generated page.
- Then still win on hierarchy: one display size for the page title, a clear label/body/caption scale, and tabular numerals for any stat or timer.
- Space: generous padding (16 to 24px in cards), consistent radius (8 to 12px), 1px borders from a neutral tone rather than heavy shadows.
- Motion, and this applies to every archetype including tools and dashboards: 150 to 250ms ease-out transitions on state changes, scroll-triggered reveals via IntersectionObserver (fade plus a 12 to 24px rise, staggered children, once only), one entrance sequence for the header or hero on load, and hover lift on cards using transform only. Plus at most one slow ambient loop where it depicts something true about the subject (steam off a mug, a plant leaning to light, a record turning, a timer breathing). Gate everything behind prefers-reduced-motion. An app that only animates on click feels like a form; ambient motion that depicts nothing is what to cut, not motion as such.
- Depth is allowed everywhere too: a subtle radial glow, a faint grid or noise layer, gradient text on the one headline that earns it. At most two such devices per screen, chosen for the subject.
- Draw the subject, do not only typeset it. Render its characteristic object as inline SVG and use it structurally: books become spines on a shelf, plants become pots in a row, records become sleeves, workouts become a load curve. Hand-built SVG at this scale beats an icon font or an emoji, and it is usually the difference between a designed app and a styled form.
- Personality comes from the subject: a habit tracker can celebrate a streak, a pomodoro timer can breathe. One signature moment per app, everything else quiet.

## Marketing sites (the Framer bar)

When the plan's archetype is "site" (landing page, portfolio, product site), the output must feel like a designed site, not a form with a header. All of the above still applies, plus:

- Structure: sticky translucent nav (backdrop blur), full-viewport hero with one strong composition, alternating content sections, a proper footer. Use the plan's sections list as the outline.
- Motion and depth: the shared rules above already cover reveals, the entrance sequence, hover lift and the two depth devices. A site may spend its full allowance on the hero rather than spreading it thin.
- Typography: hero headline at clamp(2.5rem, 7vw, 5rem) with tight leading and letter-spacing, an eyebrow label above it, balanced text wrapping. Scale drops deliberately through the page.
- Bento or feature grids beat bullet lists. Cards carry one idea each with a visual anchor (number, icon drawn as inline SVG, or stat).
- Real copy: specific headlines about the subject, not "Welcome to our website". Social proof, pricing or FAQ sections get realistic, subject-appropriate content.
- Forms wired for real: waitlist/contact forms POST to the contract endpoint, show inline success and error states, never dead-end.

## Copy

- Sentence case, plain verbs, buttons say what they do ("Add task", not "Submit").
- Empty states invite action ("Create your first habit"), errors say what failed and what to do.
- No exclamation marks, no hype.
- Never use em dashes or en dashes anywhere in copy, code comments or generated text. Use a comma, a period, a colon or parentheses instead.
- Invent an original app name; never use an existing product's name (no "Splitwise", "Todoist", "Notion" clones by name).

## Craft principles (how the good ones think)

- The hero is a thesis. Open with the most characteristic thing in the subject's world, not a generic welcome. A big number with a small label plus a gradient accent is the template answer; only use it when it is truly the best option.
- Typography carries personality. Set a deliberate scale (one display size, clear label/body/caption steps) and let weight and spacing do the work. Tabular numerals for any stat, timer or price.
- Structure is information. Use numbered markers, eyebrows or dividers only when they encode something true about the content (a real sequence, a real hierarchy), never as decoration.
- One signature element per page: the single thing the page will be remembered by (a waveform under the headline, a recipe card texture, a breathing timer ring). Build it, usually as inline SVG, and spend the boldness there while everything around it stays quiet. A page with no signature element has failed this checklist even if every other rule passes.
- Remove one accessory before shipping: if a glow, gradient or animation does not serve the subject, cut it. This is a rule about accessories, never about the signature element or the subject's own illustration; do not economise your way to a page of plain boxes.
- Fill the fields the contract gives you. If an entity carries a description, tags, a count or a colour token, the card that renders it shows them. Empty space inside a card where real data exists is a bug, not restraint.
- Copy is design material. Name things by what the user controls ("Add recipe", not "Submit entry"), keep one name per action through the whole flow, and let empty states invite the first action.

## FinEd Saathi design direction

### Product and audience

FinEd Saathi is a voice-first Indian financial-market tutor. It teaches beginners what products, fees, taxes and risks mean in simple Hinglish. The first proof explains how buying one share at ₹6 and selling it at ₹6 can still create a loss after transaction costs.

The audience is a first-time Indian investor who can place an order but may not understand the contract note, DP charge, GST, ETF, SIP or derivatives risk. The interface must feel trustworthy and patient. It must never resemble a broker order screen or imply that FinEd can execute a trade.

### Archetype

The public screen is a marketing site that transitions into a working voice app. Use the Framer bar. The page has a sticky translucent navigation bar, a full-viewport hero, alternating editorial and bento sections, a real voice-session state and a complete footer.

### Named direction: Ledger paper

The subject materials are an Indian contract note, ruled ledger paper, security paper fibres, blue registrar ink and a banknote verification stamp. The page uses a light, warm paper canvas because learning and reviewing fees are daytime editorial tasks. Deep ledger ink supplies authority. Blue is the only interactive accent. Banknote green is reserved for verified or connected status. Brick red is reserved for risk, loss or refusal.

This is not a trading terminal. There is no black candlestick wallpaper, scrolling ticker, market heatmap, bull illustration, rupee rain or green buy button.

## Brand palette

### Core colors

| Token | Hex | Use |
| --- | --- | --- |
| Paper | `#F6F2E8` | Page canvas and security-paper field |
| Surface | `#FFFCF5` | Cards, receipt and session panels |
| Ledger ink | `#15233B` | Headlines, body emphasis and primary data |
| Muted ink | `#526174` | Body copy, labels and secondary data |
| Ledger blue | `#174EA6` | Primary actions, links, selected mode and focus |
| Ledger blue hover | `#103E84` | Primary hover and active state |
| Blue wash | `#EAF1FD` | Selected mode background and quiet callout |
| Banknote green | `#1F6B4F` | Verified source, connected state and available status |
| Green wash | `#E9F4EE` | Verified status background |
| Risk brick | `#A13D35` | Loss, warning, refusal and unavailable status |
| Risk wash | `#FBEDEA` | Warning background |
| Ledger rule | `#D8D0C0` | Borders, dividers and receipt rules |
| Soft rule | `#E9E3D7` | Interior row separators and grid lines |

### Contrast contract

- Ledger ink on Paper: 14.07:1.
- Muted ink on Paper: 5.66:1.
- Ledger blue on Paper: 7.02:1.
- White on Ledger blue: 7.85:1.
- Banknote green on Paper: 5.74:1.
- Risk brick on Paper: 5.81:1.

All body-text pairs pass WCAG AA. Ledger rule is structural and is never used as text.

### Color rules

1. Ledger blue is the only interactive color.
2. Banknote green never means buy or profit. It means verified, connected or available.
3. Risk brick never colors an action. It labels risk, loss, refusal or missing certainty.
4. Gain and loss always include a sign or word. Color is supplementary.
5. Gold mode may draw a gold-line inline icon, but gold does not become a second page accent.

## Typography

Load deliberate Google fonts with preconnects for `https://fonts.googleapis.com` and `https://fonts.gstatic.com`.

- **Display and headings:** Manrope, weights 600 and 700. Its open shapes feel current and friendly without looking playful.
- **Body and controls:** Source Sans 3, weights 400 and 600. It remains readable in Hinglish, dense explanations and small mobile layouts.
- **Amounts, dates and source labels:** IBM Plex Mono, weights 400 and 500. Use it only for measured or machine-produced content.

### Scale

- Hero: `clamp(2.5rem, 7vw, 5rem)`, weight 700, line height 0.98, tracking `-0.045em`, maximum 13ch.
- Section title: `clamp(2rem, 4vw, 3.5rem)`, weight 700, line height 1.04, maximum 18ch.
- Card title: `clamp(1.05rem, 2vw, 1.3rem)`, weight 600.
- Lede: `clamp(1.05rem, 2vw, 1.25rem)`, line height 1.55, maximum 58ch.
- Body: 1rem, line height 1.65, maximum 68ch.
- Label: 0.75rem, weight 600, uppercase, tracking 0.08em.
- Caption: 0.875rem, line height 1.5.
- Data: 0.875rem IBM Plex Mono with tabular numerals.

Use sentence case for visible copy. Uppercase is limited to short machine labels and eyebrows.

## Spacing, radius and depth

- Content width: 1180px maximum with 24px desktop gutters and 16px mobile gutters.
- Section spacing: 112px desktop, 80px tablet and 64px mobile.
- Card padding: 24px desktop and 18px mobile.
- Radius: 10px for controls and 12px for cards. The receipt may use 8px to feel like paper, not an app card.
- Borders: 1px Ledger rule. Interior dividers use Soft rule.
- Touch targets: at least 40px, with 44px preferred for primary controls.

Spend the two permitted depth devices in the hero:

1. A faint security-paper fibre pattern drawn with CSS or inline SVG at less than 5 percent opacity.
2. A restrained radial Ledger blue glow behind the fee receipt at less than 10 percent opacity.

Do not add gradient text. Do not put glows behind every card. Cards use borders and surface contrast rather than heavy shadows. The hero receipt may use one soft paper shadow because it depicts a physical sheet.

## Information architecture

### 1. Sticky navigation

The navigation is translucent Paper with backdrop blur and a bottom Ledger rule after scroll.

- Left: original FinEd Saathi wordmark with a small hand-drawn ledger mark.
- Middle or right: `How it works`, `Topics`, `Why the loss` and `Sources` anchors on desktop.
- Primary action: `Talk to FinEd Saathi`.
- Mobile: wordmark and one working menu button. The menu exposes the same anchors and action with focus management.
- A compact status line names `Financial Services` and `Murf Falcon 2` without pretending they are navigation links.

### 2. Full-viewport hero

Eyebrow:

`VOICE-FIRST FINANCIAL LITERACY FOR INDIA`

Headline:

`Price same tha. Phir loss kahan se hua?`

Lede:

`FinEd Saathi Indian market concepts, charges and risks ko simple Hinglish mein samjhata hai. Ask by voice, see the math, and verify the source.`

Primary action: `Talk to FinEd Saathi`.

Secondary action: `See the ₹6 breakdown`. It scrolls to the real explanation panel.

Fine print:

`Education only. FinEd does not recommend or execute trades and never asks for your broker password, PIN or OTP.`

The left column carries the thesis. The right column carries the signature receipt. At 360px, the receipt follows the actions and remains fully readable without horizontal scroll.

### 3. Signature element: the ₹6 fee receipt

Build an original inline SVG receipt and use it structurally in the hero. The outline resembles a compact contract note with ruled rows and a restrained torn-paper edge. It is not a screenshot and not a placeholder image.

The receipt reads:

| Row | Value |
| --- | ---: |
| Buy value | ₹6.00 |
| Sell value | ₹6.00 |
| Price P&L | ₹0.00 |
| Illustrative charges | about ₹35.41 |
| Net result | about −₹35.41 |

The receipt header says `NSE delivery illustration` and the footer says `Assumptions and effective schedule shown below`. A visible caption explains that the user's historical ₹50 loss may differ because of trade date, promotion, DP debits, partial fills, extra services, aggregation or rounding.

On first load, the receipt rows may reveal once in sequence and the charge total may count up. Reduced motion shows the final complete receipt immediately. There is no looping price animation.

### 4. Topic bento

Heading: `Aaj market mein kya samajhna hai?`

Render the exact eight learning modes as a responsive accessible radio group. The visual composition is a bento grid, not eight identical buttons. Each card has one hand-built inline SVG anchor, its name, a description and a compact key label.

| Mode | Card idea |
| --- | --- |
| Stocks | Share certificate lines and ownership fraction |
| Mutual Funds & SIPs | Repeating monthly ledger entries flowing into one basket |
| ETFs | A basket crossing an exchange rule |
| Gold | Coin, tax receipt and regulated-product split |
| F&O | Payoff line with bounded and unbounded risk zones |
| IPOs | Application form moving to allotment boxes |
| Bonds | Coupon strip and maturity timeline |
| Ask Anything | Voice waveform entering an open ledger page |

Selected cards use Blue wash, a Ledger blue border and `aria-checked="true"`. Hover lifts the card 3px using transform only. Focus-visible uses a 3px Ledger blue outline. During a call all cards become disabled with an explicit `Mode locked for this call` explanation.

Selecting F&O reveals a Risk wash panel before connection:

`F&O can create rapid and substantial losses. This mode teaches mechanics and risk only. It does not provide calls or strategies for a live trade.`

### 5. How it works

Use three numbered editorial steps because they encode a real sequence:

1. Choose a topic.
2. Ask in Hindi, English or Hinglish.
3. Hear the explanation and inspect the math and sources.

Each step includes a small inline SVG that depicts the action. The third step shows a source citation and date, not a generic checkmark.

### 6. The ₹6 breakdown

Heading: `Price loss zero tha. Cost loss zero nahi tha.`

Use a wide calculation panel with a receipt column and a plain-language explanation column. Fee rows follow this order:

1. Trade value and market P&L.
2. Brokerage and fixed broker charges.
3. Statutory and exchange charges.
4. GST.
5. DP or demat debit charges.
6. Total charges, net result, fee-to-investment ratio and break-even.

All values are right-aligned IBM Plex Mono with tabular figures. The total row has a stronger top rule. An estimate badge names every assumption that prevents exact historical reconstruction.

### 7. Voice-session proof

Heading: `Sunega bhi. Samjhayega bhi.`

The proof panel contains the exact signature transcript:

`Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua.`

The assistant response distinguishes price P&L from costs, asks one missing detail at a time and never claims that ₹50 is the exact current calculation. The visible transcript keeps Markdown source links clickable. Spoken audio removes URLs but preserves source names.

An inline SVG waveform can be the single ambient loop only while a real session is connected and audio is active. It freezes when idle and when reduced motion is enabled.

### 8. Source trust section

Heading: `Broker ka answer akela final answer nahi hai.`

Use an asymmetric bento with real source classes:

- Regulator and government.
- Exchange.
- Broker pricing and support.
- Broker education.

The visual hierarchy shows `regulator > exchange > broker pricing > broker support > broker education`. Each sourced result includes publisher, title, applicability date, last-verified date and a real link. Do not claim that every Angel One page has been crawled. Call the corpus curated and versioned.

### 9. Capability and boundary grid

Use factual cards with visual anchors:

- 8 learning modes.
- Nikhil, Conversational, Murf Falcon 2.
- Angel One as the first broker baseline.
- One deterministic delivery-cost calculator.
- No recommendations.
- No trade execution.
- No broker credentials.
- F&O education and simulation only.

No invented user count, testimonial, rating, return, savings number or latency figure may appear. Measured latency can be added only after a real recorded session.

### 10. FAQ

Use working disclosure buttons with keyboard support. Include only questions beginners actually need:

- Kya FinEd mujhe stock recommend karega?
- ₹50 aur current estimate alag kyun ho sakte hain?
- ETF aur mutual fund mein basic difference kya hai?
- Kya FinEd mera Angel One account access karta hai?
- Sources kitni baar update hote hain?

The closed, open, focus, disabled and error states are designed. The answer never hides the education-only boundary.

### 11. Final action and footer

Final heading: `Agla trade nahi. Agla concept samjho.`

Primary action: `Talk to FinEd Saathi`.

The footer contains the product name, Financial Services track, education-only boundary, source methodology link, Murf attribution and public repository link when available. Do not render a dead social icon or placeholder legal link.

## Connected voice app

The voice state keeps the same Ledger paper identity.

- The active mode appears in the session header and cannot change mid-call.
- Connection, listening, thinking, speaking, reconnecting and failed states each have plain text plus a visual state.
- The audio visualizer uses Ledger blue and moves only when real audio activity exists.
- Microphone and disconnect controls use real buttons with 44px targets.
- Transcript is open by default on desktop for the Day 1 recording and toggleable on mobile.
- An empty transcript says `Ask your first market question` and suggests the exact ₹6 prompt.
- Loading says `Connecting to FinEd Saathi`.
- Error copy says what failed and offers `Try connecting again`.
- Assistant Markdown sources remain clickable in text. URLs are stripped only from TTS input.
- Calculation output uses the same fee panel and provenance pattern as the landing proof.

## Financial-data rules

### Currency and numbers

- Prefix rupee values with `₹` and use Indian grouping where useful, for example `₹1,25,000`.
- Display charge totals to two decimal places unless the calculator contract requires otherwise.
- Keep full Decimal precision in domain code and round only for display.
- Right-align amounts and percentages with tabular figures.
- Pair each percentage with its base, for example `GST, 18% of taxable charges`.
- Always label an amount as exact, current illustration, historical estimate or user-provided value.

### Provenance and dates

Every fee, tax, rule or definition exposes publisher, source title, applicability date, last-verified date and link. Human-facing dates use `DD Mon YYYY`. ISO dates appear only in machine readouts and tool data.

Conflicting sources are not blended. Show the higher-authority current source and state the conflict plainly.

### Risk and persuasion

- Risk sits beside the relevant mode or claim, not only in the footer.
- Education-only text uses readable body type, never tiny legal grey text.
- Never use countdowns, urgency, streaks, confetti or green actions to push a financial decision.
- Never label a product safe, guaranteed or best.
- Do not show live prices, delayed prices, charts, portfolio balances or performance unless the product truly fetched them and displays the source and timestamp.

## Interaction state contract

Every real control covers these states:

| State | Required treatment |
| --- | --- |
| Default | Clear label and 40px minimum target |
| Hover | 150 to 250ms ease-out, transform or color only |
| Focus-visible | 3px Ledger blue outline with offset |
| Active | Immediate pressed feedback without layout shift |
| Selected | Blue wash, Ledger blue edge and semantic state |
| Disabled | Reduced contrast plus an adjacent reason |
| Loading | Stable-width label, progress cue and blocked repeat action |
| Empty | What happened and one next action |
| Error | What failed, what remains safe and how to retry |

No interaction relies on hover alone. No link or button exists without a real target or handler.

## Motion contract

- Use the installed `motion` package or IntersectionObserver. Add no animation dependency.
- Hero entrance runs once with 150 to 250ms ease-out segments.
- Scroll sections reveal once with opacity plus a 12 to 24px rise and staggered children.
- Bento cards lift at most 3px on hover using transform only.
- The receipt count-up runs once. The connected waveform is the only allowed ambient loop and only while real audio is active.
- `prefers-reduced-motion` renders the final state immediately and disables the waveform loop.
- Content is present and readable before animation code runs.

## Responsive contract

### 360px through 639px

- Single-column hero with receipt after actions.
- One-column topic bento.
- 16px page gutters and 18px card padding.
- Mobile menu manages focus and closes after navigation.
- Fee labels wrap above values when needed.
- Transcript and source URLs wrap without horizontal page scroll.

### 640px through 1023px

- Hero may use a balanced two-column layout if both columns remain at least 280px.
- Topic bento uses 6 columns with varied spans.
- Calculation and source sections stack when their reading measure would become cramped.

### 1024px through 1440px

- Hero uses a 7 to 5 text-to-receipt grid.
- Topic bento uses 12 columns with varied spans.
- Content never exceeds 1180px.
- Large empty margins remain Paper, not decorative filler.

At every size, the viewport meta tag is exact, page overflow is absent and touch targets remain at least 40px.

## Copy voice

- Patient, specific and plain.
- Natural Hinglish in product examples, clear English in control labels where it reduces ambiguity.
- One question at a time.
- No hype, exclamation marks, em dashes or en dashes.
- No assured returns, recommendations, targets, signals or personalised allocation.
- Call an illustration an illustration and an estimate an estimate.
- Button labels describe the action: `Talk to FinEd Saathi`, `See the ₹6 breakdown`, `Try connecting again`.

## Implementation acceptance checklist

- [ ] The attached generated-app rules remain present verbatim above the FinEd direction.
- [ ] Exact viewport meta tag is present once.
- [ ] Layout works without horizontal scroll from 360px through 1440px.
- [ ] Manrope, Source Sans 3 and IBM Plex Mono load deliberately with Google Fonts preconnects.
- [ ] Palette tokens match this document and tested text pairs pass 4.5:1.
- [ ] Hero is full viewport and contains the inline SVG ₹6 receipt.
- [ ] The security-paper pattern and receipt glow are the only two hero depth devices.
- [ ] Eight modes render in a varied bento radio group with real states.
- [ ] F&O warning appears before connection.
- [ ] Every visible control works and has hover, focus-visible, disabled, loading and error treatment where applicable.
- [ ] Landing and connected states show the education-only boundary.
- [ ] The historical ₹50 memory is never presented as the exact current result.
- [ ] Currency, percentages, dates and sources follow the financial-data rules.
- [ ] Transcript is open by default on desktop.
- [ ] Murf Falcon 2 and Nikhil attribution is visible and accurate.
- [ ] Reduced motion shows complete static content.
- [ ] No placeholder image, lorem ipsum, fake testimonial, fake metric or dead link ships.
- [ ] Browser screenshots at 360px, 768px and 1440px are inspected against this file before handoff.
