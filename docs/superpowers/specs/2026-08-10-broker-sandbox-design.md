# FinEd Saathi Broker Sandbox Design

## Objective

FinEd Saathi must teach Indian financial-market concepts with real read-only
market data, deterministic calculators and browser-local paper trading. It must
never read a learner's broker account or place, modify or cancel a real order.

This design keeps the current monolith and turns its allowed capabilities into
an explicit fail-closed contract.

## Security boundary

The application permits four tool capability classes:

1. `read_only`: retrieves public educational evidence, instrument metadata,
   timestamped market quotes or the browser-local paper portfolio summary.
2. `local_compute`: performs deterministic calculations without network or
   persistent state.
3. `consented_memory`: reads, saves or deletes the small allowlisted learning
   memory. Save and delete operations retain their explicit-consent contract.
4. `paper_simulation`: opens the browser-local practice dashboard or prepares
   an expiring virtual order draft.

There is no real-money, broker-account or broker-order capability class. Agent
startup must reject an unclassified tool or a manifest containing a forbidden
capability.

The Angel One adapter is restricted to exact request definitions for:

- `POST /rest/secure/angelbroking/market/v1/quote/`
- `POST /rest/secure/angelbroking/order/v1/searchScrip`
- `POST /rest/secure/angelbroking/historical/v1/getCandleData`

The second path contains `order/v1` in Angel One's API naming but is an
instrument search endpoint. The historical endpoint is limited to `ONE_DAY`
candles and two bounded date windows used to locate entry and valuation closing
prices. No caller can supply a URL, host, HTTP method or arbitrary path. The
adapter rejects every request not represented by one of these three internal
request definitions.

FinEd must never expose or implement broker endpoints for account profile,
funds, holdings, positions, order history, trade history, order placement,
order modification or order cancellation.

Broker secrets remain backend-only. They must never enter a system prompt,
model message, tool argument, tool result, browser payload or application log.
The model can choose among registered tools but cannot construct a broker HTTP
request.

This boundary prevents model misuse and prompt injection from reaching a real
trade path. It does not claim to protect against a fully compromised host or a
stolen Angel One access token. A separate read-only gateway is the future
upgrade if FinEd becomes a public multi-user service.

## Existing tool classification

| Tool | Capability |
| --- | --- |
| `lookup_caller_memory` | `consented_memory` |
| `save_caller_memory` | `consented_memory` |
| `forget_caller_memory` | `consented_memory` |
| `search_market_knowledge` | `read_only` |
| `get_market_quote` | `read_only` |
| `search_market_instruments` | `read_only` |
| `calculate_historical_return` | `read_only` |
| `open_paper_trading_dashboard` | `paper_simulation` |
| `prepare_paper_order` | `paper_simulation` |
| `get_paper_portfolio_summary` | `read_only` |
| `calculate_angel_one_trade_cost` | `local_compute` |

The external MCP server continues exposing only `get_market_quote` and
`search_market_instruments`. Both remain annotated as read-only,
non-destructive and idempotent. Historical return calculation remains an
in-process voice-agent tool so its provider result can be combined with a
bounded deterministic calculation and fixed educational warnings.

## Historical return tool

### `calculate_historical_return`

Inputs identify one provider-resolved NSE or BSE cash-market instrument, a
strict purchase date, a strict valuation date and a positive bounded rupee
amount. The adapter requests only daily candles from two short windows: the
first available close on or after the purchase date and the last available
close on or before the valuation date. It never downloads account history or
broker trade history.

The deterministic result uses whole units and retains uninvested cash. It
returns the entry and valuation dates actually used, both closing prices,
units, leftover cash, final value, absolute gain or loss and percentage return.
It labels the result as an unadjusted historical illustration based on daily
closes. It always states that dividends, splits, bonus issues, fees, taxes and
inflation are excluded, so the result is not a total-return figure, forecast or
recommendation.

## New educational tools

### `calculate_sip_projection`

Inputs are a positive monthly contribution, a bounded duration and a
learner-supplied illustrative annual return rate. The deterministic result
includes total contributions, projected value and illustrated growth. It must
state that the return is an assumption, not a forecast or recommendation.

### `calculate_gold_purchase_cost`

Inputs identify physical gold or a gold ETF before any calculation. Physical
gold uses a dated local GST schedule and optional user-supplied making charges.
Gold ETF requests do not apply physical-gold GST and instead explain that
brokerage and market charges depend on the trade. Unsupported products or
dates fail without guessing.

### `calculate_fno_payoff`

Inputs define one hypothetical long call, long put or futures position with a
bounded quantity and user-supplied prices. The result shows expiry payoff,
maximum loss where mathematically bounded and break-even where defined. It
does not use a live quote, suggest a strike, calculate a signal, prepare an
order or claim likely returns. The F&O risk warning is always returned.

All three tools use finite numeric bounds, reject NaN and infinity, cap output
size and return structured values suitable for natural speech.

## Data and control flow

1. The participant supplies a learning question.
2. Deterministic pre-LLM guardrails reject explicit real-trade, credential or
   account-access requests before tool selection.
3. The model can select only tools present in the validated capability
   manifest.
4. Read-only broker calls pass through the exact Angel One request allowlist.
5. Local calculators execute pure functions without network access.
6. Paper drafts are sent only to the authenticated participant's browser and
   require explicit browser confirmation before changing the virtual ledger.
7. Responses label data provenance, applicability date and whether a value is
   live, local or illustrative.

## Failure behavior

- A request for a real trade or broker-account data receives a fixed refusal
  plus a safe educational or paper-trading alternative.
- Missing or rejected Angel One credentials produce the existing fixed
  market-data-unavailable response.
- Unsupported calculator inputs produce fixed tool errors without partial
  calculations.
- An invalid capability manifest prevents worker startup.
- Tool errors never include provider responses, secrets, request headers or
  stack traces in learner-visible output.

## Verification strategy

Implementation follows red-green-refactor development.

Required tests will prove:

- every registered tool has one allowed capability
- no real-money or broker-account capability can be registered
- the Angel One transport accepts the exact quote and instrument-search operations
- the Angel One transport accepts the exact bounded historical-candle operation
- raw URLs, alternate methods and order/account endpoints are rejected
- MCP exposes only the two read-only market-data tools
- prompt-injection text cannot create an unavailable tool or arbitrary request
- real-trade intent receives deterministic refusal in English, Hindi and common
  bilingual phrasing
- paper activity cannot mutate or query an Angel One account
- each new calculator validates bounds, returns deterministic results and
  includes the required educational warning
- historical return requests use bounded entry and valuation windows, select
  the correct available closes and preserve whole-unit leftover cash
- existing voice, RAG, memory, quote and paper-trading tests remain green

## Documentation and deployment

The root README will list all tool capabilities and state that Angel One data
is market-data-only. It will distinguish live quotes from local schedules and
illustrative calculations.

The current monolith is suitable for the challenge and a controlled demo. A
public multi-user deployment must also rotate previously exposed credentials,
add authenticated and rate-limited LiveKit token issuance and consider moving
broker credentials behind a separate read-only gateway.
