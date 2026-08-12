from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from livekit.agents import Agent, ChatContext, ModelSettings, RunContext, ToolError

from fined.agent import (
    FinEdAssistant,
    ParticipantProfile,
    SessionState,
    build_greeting,
    build_system_prompt,
    parse_participant_profile,
)
from fined.calculator import ScheduleConfigurationError, UnsupportedScheduleError
from fined.knowledge.index import SearchHit
from fined.market_data.angel_one import create_market_data_provider
from fined.market_data.models import (
    HistoricalClose,
    HistoricalPricePair,
    HistoricalPriceRequest,
    InstrumentSearchRequest,
    MarketInstrument,
    MarketQuote,
    QuoteRequest,
)
from fined.market_data.provider import (
    MARKET_DATA_UNAVAILABLE_MESSAGE,
    MarketDataUnavailableError,
)
from fined.memory import SQLiteCallerMemoryStore
from fined.modes import LearningMode
from fined.outbound import PAPER_PRACTICE_REMINDER
from fined.paper_trading import (
    PaperDashboardAck,
    PaperDraftAck,
    PaperOrderDraft,
    PaperPortfolioSummary,
    PaperTradingUIUnavailableError,
)


@dataclass
class FakeRetriever:
    hits: list[SearchHit]
    calls: list[dict[str, object]] = field(default_factory=list)

    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]:
        self.calls.append(
            {
                "query": query,
                "learning_mode": learning_mode,
                "as_of_date": as_of_date,
                "broker": broker,
                "top_k": top_k,
            }
        )
        return self.hits


@dataclass
class FakeMarketDataProvider:
    quote: MarketQuote | None = None
    calls: list[QuoteRequest] = field(default_factory=list)
    instruments: tuple[MarketInstrument, ...] = ()
    search_calls: list[InstrumentSearchRequest] = field(default_factory=list)
    historical_prices: HistoricalPricePair | None = None
    historical_calls: list[HistoricalPriceRequest] = field(default_factory=list)

    async def get_quote(self, request: QuoteRequest) -> MarketQuote:
        self.calls.append(request)
        if self.quote is None:
            raise MarketDataUnavailableError("provider detail must stay hidden")
        return self.quote

    async def search_instruments(
        self, request: InstrumentSearchRequest
    ) -> tuple[MarketInstrument, ...]:
        self.search_calls.append(request)
        return self.instruments

    async def get_historical_prices(
        self, request: HistoricalPriceRequest
    ) -> HistoricalPricePair:
        self.historical_calls.append(request)
        if self.historical_prices is None:
            raise MarketDataUnavailableError("provider detail must stay hidden")
        return self.historical_prices


@dataclass
class FakePaperTradingBridge:
    draft: PaperOrderDraft | None = None
    open_calls: int = 0
    summary_calls: int = 0
    fail: bool = False
    prepared: bool = True
    prepare_calls: int = 0
    confirm_calls: list[str] = field(default_factory=list)

    async def open_dashboard(self) -> PaperDashboardAck:
        self.open_calls += 1
        if self.fail:
            raise PaperTradingUIUnavailableError()
        return PaperDashboardAck(opened=True)

    async def prepare_order(self, draft: PaperOrderDraft) -> PaperDraftAck:
        self.prepare_calls += 1
        self.draft = draft
        if self.fail:
            raise PaperTradingUIUnavailableError()
        return PaperDraftAck(prepared=self.prepared, draft_id=draft.draft_id)

    async def confirm_order(self, draft_id: str):
        self.confirm_calls.append(draft_id)
        if self.fail or self.draft is None or self.draft.draft_id != draft_id:
            raise PaperTradingUIUnavailableError()
        return SimpleNamespace(
            draft_id=self.draft.draft_id,
            side=self.draft.side,
            trading_symbol=self.draft.trading_symbol,
            quantity=self.draft.quantity,
            fill_price_paise=self.draft.price_paise,
            simulated_at=datetime.now(UTC),
            cash_paise=9_749_900,
        )

    async def get_portfolio_summary(self) -> PaperPortfolioSummary:
        self.summary_calls += 1
        if self.fail:
            raise PaperTradingUIUnavailableError()
        return PaperPortfolioSummary(
            cash_paise=9_500_000,
            holdings_cost_basis_paise=500_000,
            cash_plus_cost_basis_paise=10_000_000,
        )


@dataclass
class FakeOutboundCallControl:
    end_calls: int = 0
    fail: bool = False

    async def end_call(self) -> None:
        self.end_calls += 1
        if self.fail:
            raise RuntimeError("private carrier failure")


@dataclass
class FakeEscalationStore:
    created: list[tuple[object, bool]] = field(default_factory=list)
    fail: bool = False

    def create(self, request: object, *, consent_confirmed: bool):
        self.created.append((request, consent_confirmed))
        if self.fail:
            raise RuntimeError("private database detail")
        candidate = cast(SimpleNamespace, request)
        return SimpleNamespace(
            reference_id="HELP-A1B2C3D4",
            reason=candidate.reason,
            urgency=candidate.urgency,
            caller_language=candidate.caller_language,
            summary=candidate.summary,
            checks=tuple(candidate.checks),
            follow_up=candidate.follow_up,
            status="open",
            created_at=datetime(2026, 8, 12, 6, 30, tzinfo=UTC),
        )

    def list_open(self):
        return []


@dataclass
class FakeHumanHelpBridge:
    requests: list[dict[str, object]] = field(default_factory=list)
    fail: bool = False

    async def show_request(self, request: dict[str, object]):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("private RPC detail")
        return SimpleNamespace(opened=True)


def _context(state: SessionState) -> RunContext[SessionState]:
    return cast(RunContext[SessionState], SimpleNamespace(userdata=state))


def _paper_instrument(
    *,
    exchange: str = "NSE",
    symbol_token: str = "2885",
    trading_symbol: str = "RELIANCE-EQ",
    series: str | None = "EQ",
) -> MarketInstrument:
    return MarketInstrument(
        exchange=exchange,
        symbol_token=symbol_token,
        trading_symbol=trading_symbol,
        series=series,
    )


def _paper_state(
    *,
    provider: FakeMarketDataProvider,
    bridge: FakePaperTradingBridge,
    profile: ParticipantProfile | None = None,
    instrument: MarketInstrument | None = None,
) -> SessionState:
    resolved = instrument or _paper_instrument()
    return SessionState(
        profile=profile or ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        paper_trading=bridge,
        resolved_market_instruments={
            (resolved.exchange, resolved.symbol_token): resolved
        },
    )


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        "",
        "   ",
        "not json",
        "null",
        "[]",
        '"stocks"',
        '{"learning_mode":"stocks","unexpected":"do not accept"}',
        '{"mode":"stocks"}',
        '{"learning_mode":"crypto"}',
    ],
)
def test_participant_profile_defaults_untrusted_metadata_to_general(
    metadata: str | None,
) -> None:
    # Catches permissive parsing of malformed, non-object, or extra-field metadata.
    assert parse_participant_profile(metadata) == ParticipantProfile(
        learning_mode=LearningMode.GENERAL
    )


def test_participant_profile_accepts_only_the_supported_learning_mode_field() -> None:
    # Catches accidental rejection of the one valid metadata shape.
    assert parse_participant_profile('{"learning_mode":"mutual_funds"}') == (
        ParticipantProfile(learning_mode=LearningMode.MUTUAL_FUNDS)
    )


def test_participant_metadata_limit_is_1024_utf8_bytes_inclusively() -> None:
    # Catches character-count limits and off-by-one byte limits.
    payload = json.dumps({"learning_mode": "etfs"}, separators=(",", ":"))
    at_limit = " " * (1024 - len(payload.encode("utf-8"))) + payload
    above_limit = f"{at_limit} "
    multibyte_duplicate = (
        '{"learning_mode":"' + "₹" * 340 + '","learning_mode":"stocks"}'
    )
    assert len(multibyte_duplicate) < 1024
    assert len(multibyte_duplicate.encode("utf-8")) > 1024

    assert parse_participant_profile(at_limit).learning_mode is LearningMode.ETFS
    assert parse_participant_profile(above_limit).learning_mode is LearningMode.GENERAL
    assert (
        parse_participant_profile(multibyte_duplicate).learning_mode
        is LearningMode.GENERAL
    )


def test_prompt_carries_supported_scope_and_financial_safety_contract() -> None:
    # Catches prompt regressions that broaden the tutor into advice or credential access.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS))

    for concept in (
        "stocks",
        "mutual_funds",
        "etfs",
        "gold",
        "fno",
        "ipos",
        "bonds",
        "general",
    ):
        assert concept in prompt
    assert "education only" in prompt.casefold()
    for prohibited in (
        "recommendations",
        "targets",
        "signals",
        "assured returns",
        "portfolio allocation",
        "trade execution",
        "broker password",
        "PIN",
        "OTP",
        "full account number",
        "credentials",
    ):
        assert prohibited.casefold() in prompt.casefold()
    assert (
        "Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua."
        in prompt
    )
    assert "₹35.41" in prompt
    assert "historical ₹50" in prompt
    assert "selected learning mode: stocks" in prompt.casefold()


def test_prompt_requires_deterministic_tools_sources_and_honest_abstention() -> None:
    # Catches fee fabrication, missing source precedence, and unsupported live F&O help.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.FNO)).casefold()

    for required in (
        "one missing calculation input at a time",
        "broker, delivery versus intraday, date, exchange, quantity, buy price, and sell price",
        "delivery-only",
        "do not call it for intraday or f&o",
        "never reconstruct fee math",
        "use retrieval",
        "regulator and government sources",
        "outrank exchanges",
        "outrank broker pricing",
        "markdown source links",
        "no spoken urls",
        "high risk",
        "educational simulation means payoff examples only",
        "could not be verified",
    ):
        assert required in prompt


def test_prompt_matches_the_users_language_register() -> None:
    # Catches forced Hinglish or rejection of the Day 2 code-mixed requirement.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "reply entirely in english",
        "reply entirely in hindi",
        "devanagari",
        "code-mixed",
        "matching code-mixed register",
        "do not introduce code-mixing",
        "continue in english or hindi",
        "do not repeat the remembered romanized-hindi sentence",
    ):
        assert required in prompt


def test_prompt_defines_day_two_persona_objectives_and_limits() -> None:
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "identity",
        "voice-first indian financial-markets tutor",
        "objectives",
        "successful call",
        "never ask for an otp",
        "never recommend buying, selling, or holding",
        "never provide targets, signals, guaranteed returns",
        "never execute a real broker trade",
        "sebi-registered investment adviser",
        "official broker support",
        "qualified tax professional",
        "boundary plainly",
        "one-sentence reason",
        "allowed alternative",
        "twenty words or fewer",
        "one question",
    ):
        assert required in prompt


def test_prompt_reconciles_the_remembered_fifty_rupees_without_guessing() -> None:
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS))
    normalized = prompt.casefold()

    assert (
        "Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua."
        in prompt
    )
    for required in (
        "treat ₹50 as unresolved",
        "do not guess or invent a scenario that matches ₹50",
        "contract-note total charges, ledger or available funds, or p&l",
        "trade date",
        "delivery versus intraday",
        "executed buy order count",
        "executed sell order count",
        "sell-side dp transaction or debit count",
        "promotion status",
        "separate account or service charge",
        "contract-note or trades & charges rows outrank a generic estimate",
        "lower of ₹20 or 0.1% per executed order, subject to a ₹5 minimum",
        "one executed buy order, one executed sell order, and one sell-side dp debit",
        "590.22%",
        "₹41.46",
    ):
        assert required in normalized


def test_greeting_names_track_topic_and_adds_fno_risk_line() -> None:
    # Catches generic greetings and omission of the mandatory F&O warning.
    stocks = build_greeting(ParticipantProfile(LearningMode.STOCKS))
    fno = build_greeting(ParticipantProfile(LearningMode.FNO))

    assert "Indian markets learning companion" in stocks
    assert "Financial Services" not in stocks
    assert "track" not in stocks.casefold()
    assert "FinEd Saathi" in stocks
    assert "Stocks" in stocks
    assert "English, Hindi, or both" in stocks
    assert "education, not investment advice" in stocks
    assert len(stocks) < 320
    assert "Indian markets learning companion" in fno
    assert "Financial Services" not in fno
    assert "track" not in fno.casefold()
    assert "F&O" in fno
    assert "high risk" in fno.casefold()
    assert "payoff examples" in fno.casefold()
    assert "not paper orders" in fno.casefold()
    assert "education and simulation only" not in fno.casefold()


def test_greetings_are_english_and_offer_user_led_language_choice() -> None:
    # Catches the greeting forcing Hinglish before the user has chosen a register.
    greetings = [build_greeting(ParticipantProfile(mode)) for mode in LearningMode]
    romanized_hindi = ("aaj", "aur", "hai", "mein", "nahi", "sawaal", "samjhenge")

    assert all("English, Hindi, or both" in greeting for greeting in greetings)
    assert all(
        word not in greeting.casefold()
        for greeting in greetings
        for word in romanized_hindi
    )


def test_greetings_do_not_emit_en_or_em_dashes() -> None:
    # Catches punctuation that violates the visible-copy design contract.
    greetings = [build_greeting(ParticipantProfile(mode)) for mode in LearningMode]
    prohibited_dashes = (chr(0x2013), chr(0x2014))

    assert all(
        dash not in greeting for greeting in greetings for dash in prohibited_dashes
    )


@pytest.mark.asyncio
async def test_llm_node_short_circuits_guardrails_before_provider_or_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_called = False

    async def fake_llm_node(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        yield "provider reply"

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = ChatContext.empty()
    chat_ctx.add_message(
        role="user",
        content="Give me a guaranteed F&O strategy for tomorrow.",
    )

    output = [
        chunk
        async for chunk in FinEdAssistant().llm_node(
            chat_ctx,
            [],
            ModelSettings(),
        )
    ]

    assert provider_called is False
    assert output == [
        "I can't promise returns or provide guaranteed F&O calls. Markets carry "
        "risk, and F&O can cause rapid losses. I can explain the mechanics and "
        "risk, or you can consult a SEBI-registered investment adviser."
    ]


@pytest.mark.asyncio
async def test_llm_node_delegates_safe_education_to_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_called = False

    async def fake_llm_node(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        yield "An ETF trades on an exchange."

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = ChatContext.empty()
    chat_ctx.add_message(role="user", content="What is an ETF?")

    output = [
        chunk
        async for chunk in FinEdAssistant().llm_node(
            chat_ctx,
            [],
            ModelSettings(),
        )
    ]

    assert provider_called is True
    assert output == ["An ETF trades on an exchange."]


def test_fined_assistant_defaults_to_general_and_exposes_exact_tool_names() -> None:
    # Catches a broken starter import seam or renamed LiveKit tools.
    assistant = FinEdAssistant()

    assert "selected learning mode: general" in assistant.instructions.casefold()
    assert assistant.search_market_knowledge.info.name == "search_market_knowledge"
    assert (
        assistant.calculate_angel_one_trade_cost.info.name
        == "calculate_angel_one_trade_cost"
    )
    assert assistant.get_market_quote.info.name == "get_market_quote"
    assert (
        assistant.calculate_historical_return.info.name == "calculate_historical_return"
    )
    assert (
        assistant.open_paper_trading_dashboard.info.name
        == "open_paper_trading_dashboard"
    )
    assert assistant.search_market_instruments.info.name == "search_market_instruments"
    assert assistant.prepare_paper_order.info.name == "prepare_paper_order"
    assert assistant.confirm_paper_order.info.name == "confirm_paper_order"
    assert (
        assistant.get_paper_portfolio_summary.info.name == "get_paper_portfolio_summary"
    )
    assert assistant.lookup_caller_memory.info.name == "lookup_caller_memory"
    assert assistant.save_caller_memory.info.name == "save_caller_memory"
    assert assistant.forget_caller_memory.info.name == "forget_caller_memory"
    assert assistant.end_outbound_call.info.name == "end_outbound_call"
    assert assistant.create_escalation.info.name == "create_escalation"


def test_prompt_requires_fresh_permission_for_limited_human_help() -> None:
    # Catches silent escalation, full-transcript sharing, or vague follow-up promises.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "human help",
        "suspected fraud",
        "decision the agent cannot make",
        "create_escalation",
        "ask for explicit permission",
        "do not create the request",
        "full conversation",
        "otp",
        "pin",
        "password",
        "account number",
        "reference id",
        "do not promise an immediate reply",
        "normal learning question",
        "do you recognise or authorise",
        "suspected, never confirmed fraud",
        "charge dispute, investment loss, poor return or normal market question",
    ):
        assert required in prompt


@pytest.mark.asyncio
async def test_create_escalation_requires_fresh_consent_and_shows_safe_request() -> (
    None
):
    store = FakeEscalationStore()
    bridge = FakeHumanHelpBridge()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        caller_id="learner-1",
        escalation_store=store,
        human_help=bridge,
    )
    assistant = FinEdAssistant()

    with pytest.raises(ToolError, match="explicit permission"):
        await assistant.create_escalation(
            _context(state),
            reason="suspected_fraud",
            summary="The learner reports an unrecognised account transaction.",
            checks_completed="FinEd confirmed the activity was not recognised.",
            urgency="high",
            caller_language="english",
            follow_up_method="in_app",
            consent_confirmed=False,
        )

    assert store.created == []
    assert bridge.requests == []

    result = await assistant.create_escalation(
        _context(state),
        reason="suspected_fraud",
        summary="The learner reports an unrecognised account transaction.",
        checks_completed="FinEd confirmed the activity was not recognised.",
        urgency="high",
        caller_language="english",
        follow_up_method="in_app",
        consent_confirmed=True,
    )

    assert len(store.created) == 1
    assert store.created[0][1] is True
    assert bridge.requests == [
        {
            "version": 1,
            "reference_id": "HELP-A1B2C3D4",
            "reason": "suspected_fraud",
            "summary": "The learner reports an unrecognised account transaction.",
            "checks_completed": "FinEd confirmed the activity was not recognised.",
            "urgency": "high",
            "language": "english",
            "follow_up_method": "in_app",
            "status": "open",
            "created_at": "2026-08-12T06:30:00+00:00",
        }
    ]
    assert result["created"] is True
    assert result["reference_id"] == "HELP-A1B2C3D4"
    assert result["status"] == "open"
    assert "immediate" not in str(result["message"]).casefold()


@pytest.mark.asyncio
async def test_create_escalation_is_browser_only_and_hides_internal_failures() -> None:
    outbound_state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        outbound_reminder=PAPER_PRACTICE_REMINDER,
    )
    with pytest.raises(ToolError, match="unavailable during a short outbound"):
        await FinEdAssistant().create_escalation(
            _context(outbound_state),
            reason="suspected_fraud",
            summary="An unrecognised transaction was reported.",
            checks_completed="FinEd confirmed it was not recognised.",
            urgency="high",
            caller_language="english",
            follow_up_method="in_app",
            consent_confirmed=True,
        )

    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        caller_id="learner-1",
        escalation_store=FakeEscalationStore(fail=True),
        human_help=FakeHumanHelpBridge(),
    )
    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().create_escalation(
            _context(state),
            reason="decision_review",
            summary="The learner needs a personalised investment decision.",
            checks_completed="FinEd explained the educational boundary.",
            urgency="medium",
            caller_language="english",
            follow_up_method="in_app",
            consent_confirmed=True,
        )
    assert str(failure.value) == "Human help is unavailable right now."
    assert "private" not in str(failure.value)


@pytest.mark.asyncio
async def test_created_escalation_remains_honest_when_dashboard_delivery_fails() -> (
    None
):
    store = FakeEscalationStore()
    bridge = FakeHumanHelpBridge(fail=True)
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        caller_id="learner-1",
        escalation_store=store,
        human_help=bridge,
    )

    result = await FinEdAssistant().create_escalation(
        _context(state),
        reason="decision_review",
        summary="The learner needs a human review before a large paper order.",
        checks_completed="FinEd blocked the paper draft above ₹50,000.",
        urgency="medium",
        caller_language="english",
        follow_up_method="in_app",
        consent_confirmed=True,
    )

    assert len(store.created) == 1
    assert result["created"] is True
    assert result["dashboard_opened"] is False
    assert result["reference_id"] == "HELP-A1B2C3D4"
    assert "saved" in str(result["message"]).casefold()
    assert "dashboard" in str(result["message"]).casefold()


def test_outbound_prompt_allows_confirmed_call_paper_fills_without_broker_actions() -> (
    None
):
    # Catches call paper practice becoming a real trade or skipping confirmation.
    prompt = FinEdAssistant(
        ParticipantProfile(LearningMode.STOCKS),
        outbound_reminder=PAPER_PRACTICE_REMINDER,
    ).instructions.casefold()

    assert "outbound call" in prompt
    assert "opt-in paper-trading practice reminder" in prompt
    assert "do not call lookup_caller_memory" in prompt
    assert "call end_outbound_call" in prompt
    assert "never access a broker account" in prompt
    assert "call-scoped" in prompt
    assert "₹1,00,000" in prompt
    assert "explicit confirmation" in prompt
    assert "never execute a real broker order" in prompt


@pytest.mark.asyncio
async def test_outbound_stop_tool_ends_only_a_consented_learning_reminder() -> None:
    # Catches a tool that can terminate ordinary browser calls or leaks carrier errors.
    control = FakeOutboundCallControl()
    outbound_state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        outbound_reminder=PAPER_PRACTICE_REMINDER,
        outbound_call_control=control,
    )

    result = await FinEdAssistant().end_outbound_call(_context(outbound_state))

    assert control.end_calls == 1
    assert result == {
        "ended": True,
        "message": "The consented learning reminder call is ending.",
    }

    browser_state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS), retriever=FakeRetriever([])
    )
    with pytest.raises(ToolError, match="not an outbound learning reminder"):
        await FinEdAssistant().end_outbound_call(_context(browser_state))
    assert control.end_calls == 1

    failing_state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        outbound_reminder=PAPER_PRACTICE_REMINDER,
        outbound_call_control=FakeOutboundCallControl(fail=True),
    )
    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().end_outbound_call(_context(failing_state))
    assert str(failure.value) == "The reminder call could not be ended safely."
    assert "private" not in str(failure.value)


@pytest.mark.asyncio
async def test_outbound_reminder_blocks_memory_and_browser_but_allows_paper_tools() -> (
    None
):
    # Catches the phone sandbox being unusable or leaking into browser memory.
    provider = FakeMarketDataProvider(quote=_paper_quote())
    bridge = FakePaperTradingBridge()
    state = _paper_state(provider=provider, bridge=bridge)
    state.outbound_reminder = PAPER_PRACTICE_REMINDER
    assistant = FinEdAssistant(outbound_reminder=PAPER_PRACTICE_REMINDER)

    with pytest.raises(ToolError, match="unavailable during a short outbound"):
        await assistant.lookup_caller_memory(_context(state))
    with pytest.raises(ToolError, match="unavailable during a short outbound"):
        await assistant.open_paper_trading_dashboard(_context(state))

    quote = await assistant.get_market_quote(_context(state), "NSE", "2885")
    prepared = await assistant.prepare_paper_order(
        _context(state), "buy", "NSE", "2885", 1
    )
    result = await assistant.confirm_paper_order(
        _context(state), str(prepared["draft_id"])
    )

    assert quote["is_order"] is False
    assert prepared["paper"] is True
    assert result["filled"] is True
    assert provider.calls == [QuoteRequest("NSE", "2885"), QuoteRequest("NSE", "2885")]
    assert bridge.open_calls == 0
    assert bridge.prepare_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop_request",
    [
        "stop",
        "Please stop calling me.",
        "hang up",
        "cut the call",
        "disconnect the call",
        "कॉल बंद करो",
        "फोन काट दो",
    ],
)
async def test_outbound_stop_phrase_is_handled_before_llm_generation(
    monkeypatch: pytest.MonkeyPatch, stop_request: str
) -> None:
    # Catches a model miss that leaves a caller connected after a direct stop request.
    control = FakeOutboundCallControl()
    provider_called = False

    async def fake_llm_node(*args, **kwargs):
        nonlocal provider_called
        del args, kwargs
        provider_called = True
        yield "This must not be generated."

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = ChatContext.empty()
    chat_ctx.add_message(role="user", content=stop_request)

    output = [
        chunk
        async for chunk in FinEdAssistant(
            outbound_reminder=PAPER_PRACTICE_REMINDER,
            outbound_call_control=control,
        ).llm_node(chat_ctx, [], ModelSettings())
    ]

    assert control.end_calls == 1
    assert provider_called is False
    assert output == []


@pytest.mark.asyncio
async def test_outbound_stop_detection_does_not_mistake_stop_loss_for_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches an overbroad stop matcher that terminates a legitimate lesson.
    control = FakeOutboundCallControl()

    async def fake_llm_node(*args, **kwargs):
        del args, kwargs
        yield "A stop-loss order is a risk-management instruction."

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = ChatContext.empty()
    chat_ctx.add_message(role="user", content="What is a stop-loss order?")

    output = [
        chunk
        async for chunk in FinEdAssistant(
            outbound_reminder=PAPER_PRACTICE_REMINDER,
            outbound_call_control=control,
        ).llm_node(chat_ctx, [], ModelSettings())
    ]

    assert control.end_calls == 0
    assert output == ["A stop-loss order is a risk-management instruction."]


def test_prompt_requires_lookup_and_explicit_consent_before_memory_writes() -> None:
    # Catches memory being injected into the prompt or saved on ambiguous consent.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "call lookup_caller_memory at the start of every new session",
        "ask for explicit consent immediately before every save",
        "silence, ambiguity or earlier consent do not count",
        "never save broker credentials, account numbers, pan or aadhaar",
    ):
        assert required in prompt


def test_prompt_defines_browser_only_paper_trading_safety_contract() -> None:
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "paper trading is a browser-only educational simulation with virtual money",
        "use open_paper_trading_dashboard",
        "use prepare_paper_order only after side, supported instrument, and positive whole quantity are known",
        "the tool prepares a draft",
        "use confirm_paper_order only after explicit confirmation",
        "same pending paper draft",
        "never say it filled until the browser reports a confirmed paper result",
        "never provide a recommendation or convert a paper request into a real broker action",
        "paper fills are currently limited to nse eq cash equity and etf delivery",
        "never prepare an intraday, leveraged, short-selling, or f&o paper order",
        "f&o simulation means educational payoff examples only, never a paper order",
    ):
        assert required in prompt


@pytest.mark.asyncio
async def test_confirm_paper_order_fills_only_the_matching_pending_draft() -> None:
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=_paper_quote()),
        bridge=bridge,
    )
    prepared = await FinEdAssistant().prepare_paper_order(
        _context(state), side="buy", exchange="NSE", symbol_token="2885", quantity=1
    )
    draft_id = str(prepared["draft_id"])

    result = await FinEdAssistant().confirm_paper_order(_context(state), draft_id)

    assert bridge.confirm_calls == [draft_id]
    assert result["paper"] is True
    assert result["filled"] is True
    assert result["draft_id"] == draft_id
    assert result["side"] == "buy"
    assert result["trading_symbol"] == "RELIANCE-EQ"
    assert result["quantity"] == 1
    assert state.pending_paper_drafts == {}


@pytest.mark.asyncio
async def test_confirm_paper_order_rejects_unknown_draft_without_browser_rpc() -> None:
    bridge = FakePaperTradingBridge()
    state = _paper_state(provider=FakeMarketDataProvider(), bridge=bridge)

    with pytest.raises(ToolError, match="pending paper draft"):
        await FinEdAssistant().confirm_paper_order(_context(state), "draft-unknown")

    assert bridge.confirm_calls == []


def test_prompt_requires_historical_tool_and_explains_estimate_limits() -> None:
    # Catches the model inventing past prices or presenting raw closes as total return.
    prompt = build_system_prompt(ParticipantProfile(LearningMode.STOCKS)).casefold()

    for required in (
        "use calculate_historical_return",
        "purchase date",
        "valuation date",
        "investment amount",
        "whole units",
        "unadjusted daily closing prices",
        "dividends, splits, bonus issues, fees, taxes and inflation",
        "not a total-return figure, forecast or recommendation",
    ):
        assert required in prompt


@pytest.mark.asyncio
async def test_open_paper_dashboard_calls_bridge_without_broker_action() -> None:
    bridge = FakePaperTradingBridge()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        paper_trading=bridge,
    )

    result = await FinEdAssistant().open_paper_trading_dashboard(_context(state))

    assert bridge.open_calls == 1
    assert bridge.draft is None
    assert result == {"opened": True, "paper": True, "is_order": False}


@pytest.mark.asyncio
async def test_instrument_search_preserves_ambiguous_choices_for_the_learner() -> None:
    provider = FakeMarketDataProvider(
        instruments=(
            MarketInstrument("NSE", "2885", "RELIANCE-EQ", "EQ"),
            MarketInstrument("BSE", "500325", "RELIANCE-A", "A"),
        )
    )
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        paper_trading=FakePaperTradingBridge(),
    )

    result = await FinEdAssistant().search_market_instruments(
        _context(state), query="RELIANCE"
    )

    assert provider.search_calls == [InstrumentSearchRequest(query="RELIANCE")]
    assert result == {
        "matches": [
            {
                "exchange": "NSE",
                "symbol_token": "2885",
                "trading_symbol": "RELIANCE-EQ",
                "series": "EQ",
                "is_order": False,
            },
            {
                "exchange": "BSE",
                "symbol_token": "500325",
                "trading_symbol": "RELIANCE-A",
                "series": "A",
                "is_order": False,
            },
        ],
        "requires_selection": True,
        "paper": True,
        "is_order": False,
        "message": (
            "Ask the learner to choose one exact exchange and instrument. "
            "Paper fills are currently limited to NSE EQ."
        ),
    }
    assert set(state.resolved_market_instruments) == {
        ("NSE", "2885"),
        ("BSE", "500325"),
    }


@pytest.mark.asyncio
async def test_instrument_search_removes_a_trailing_company_descriptor() -> None:
    instrument = MarketInstrument("NSE", "2885", "RELIANCE-EQ", "EQ")
    provider = FakeMarketDataProvider(instruments=(instrument,))
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        paper_trading=FakePaperTradingBridge(),
    )

    result = await FinEdAssistant().search_market_instruments(
        _context(state), query="Reliance Industries", exchange="NSE"
    )

    assert provider.search_calls == [
        InstrumentSearchRequest(query="RELIANCE", exchange="NSE")
    ]
    assert result["matches"] == [
        {
            "exchange": "NSE",
            "symbol_token": "2885",
            "trading_symbol": "RELIANCE-EQ",
            "series": "EQ",
            "is_order": False,
        }
    ]


@pytest.mark.asyncio
async def test_instrument_search_requests_a_latin_retry_for_devanagari_query() -> None:
    provider = FakeMarketDataProvider()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
    )

    with pytest.raises(ToolError, match="Latin-script company name or trading symbol"):
        await FinEdAssistant().search_market_instruments(
            _context(state), query="रिलायंस"
        )

    assert provider.search_calls == []


@pytest.mark.asyncio
async def test_bse_cash_instrument_remains_searchable_for_education() -> None:
    instrument = MarketInstrument(
        exchange="BSE",
        trading_symbol="RELIANCE",
        symbol_token="500325",
        series=None,
    )
    provider = FakeMarketDataProvider(instruments=(instrument,))
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        paper_trading=FakePaperTradingBridge(),
    )

    result = await FinEdAssistant().search_market_instruments(
        _context(state), query="RELIANCE", exchange="BSE"
    )

    assert provider.search_calls == [
        InstrumentSearchRequest(query="RELIANCE", exchange="BSE")
    ]
    assert result["matches"] == [
        {
            "exchange": "BSE",
            "symbol_token": "500325",
            "trading_symbol": "RELIANCE",
            "series": None,
            "is_order": False,
        }
    ]
    assert "Paper fills are currently limited to NSE EQ." in str(result["message"])
    assert state.resolved_market_instruments[("BSE", "500325")] == instrument
    assert set(state.resolved_market_instruments) == {("BSE", "500325")}


def _paper_quote(
    *,
    age_seconds: int = 0,
    exchange: str = "NSE",
    symbol_token: str = "2885",
    trading_symbol: str = "RELIANCE-EQ",
) -> MarketQuote:
    received_time = datetime.now(UTC)
    exchange_time = received_time - timedelta(seconds=age_seconds)
    return MarketQuote(
        exchange=exchange,
        symbol_token=symbol_token,
        trading_symbol=trading_symbol,
        last_traded_price=Decimal("2500.50"),
        close_price=Decimal("2490.00"),
        provider="Angel One SmartAPI",
        exchange_time=exchange_time,
        received_time=received_time,
    )


@pytest.mark.asyncio
async def test_prepare_order_uses_provider_quote_not_model_price() -> None:
    bridge = FakePaperTradingBridge()
    provider = FakeMarketDataProvider(quote=_paper_quote())
    state = _paper_state(provider=provider, bridge=bridge)

    result = await FinEdAssistant().prepare_paper_order(
        _context(state), side="buy", exchange="NSE", symbol_token="2885", quantity=1
    )

    assert provider.calls == [QuoteRequest("NSE", "2885")]
    assert result["requires_browser_confirmation"] is True
    assert result["filled"] is False
    assert bridge.draft is not None
    assert bridge.draft.price_paise == 250_050
    assert bridge.draft.charge_status == "estimated"
    assert bridge.draft.expires_at - bridge.draft.quote_time == timedelta(seconds=30)
    assert bridge.draft.draft_id
    assert state.pending_paper_drafts == {bridge.draft.draft_id: bridge.draft}


@pytest.mark.asyncio
async def test_prepare_order_above_fifty_thousand_requires_human_review() -> None:
    bridge = FakePaperTradingBridge()
    provider = FakeMarketDataProvider(quote=_paper_quote())
    state = _paper_state(provider=provider, bridge=bridge)

    with pytest.raises(ToolError, match="above ₹50,000") as failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state),
            side="buy",
            exchange="NSE",
            symbol_token="2885",
            quantity=20,
        )

    assert "decision_review" in str(failure.value)
    assert "explicit permission" in str(failure.value)
    assert bridge.prepare_calls == 0
    assert state.pending_paper_drafts == {}


@pytest.mark.asyncio
async def test_prepare_order_does_not_track_draft_without_browser_acknowledgement() -> (
    None
):
    bridge = FakePaperTradingBridge(prepared=False)
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=_paper_quote()),
        bridge=bridge,
    )

    with pytest.raises(ToolError, match="Paper trading is unavailable"):
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert bridge.draft is not None
    assert state.pending_paper_drafts == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instrument_fields",
    [
        {"trading_symbol": "RELIANCE-EQ", "series": "EQ"},
        {"trading_symbol": "NIFTYBEES-EQ", "series": "EQ"},
    ],
)
async def test_prepare_order_accepts_provider_resolved_allowlisted_delivery_instrument(
    instrument_fields: dict[str, object],
) -> None:
    instrument = _paper_instrument(**instrument_fields)  # type: ignore[arg-type]
    quote = _paper_quote(
        exchange=instrument.exchange,
        symbol_token=instrument.symbol_token,
        trading_symbol=instrument.trading_symbol,
    )
    provider = FakeMarketDataProvider(quote=quote)
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=provider,
        bridge=bridge,
        instrument=instrument,
    )

    await FinEdAssistant().prepare_paper_order(
        _context(state),
        "buy",
        instrument.exchange,
        instrument.symbol_token,
        1,
    )

    assert provider.calls == [
        QuoteRequest(instrument.exchange, instrument.symbol_token)
    ]
    assert bridge.draft is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instrument_fields",
    [
        {"trading_symbol": "RELIANCE-BE", "series": "BE"},
        {"trading_symbol": "RELIANCE-BL", "series": "BL"},
        {
            "exchange": "BSE",
            "symbol_token": "500325",
            "trading_symbol": "RELIANCE-A",
            "series": "A",
        },
    ],
)
async def test_prepare_order_rejects_unsupported_provider_series_before_quote(
    instrument_fields: dict[str, object],
) -> None:
    instrument = _paper_instrument(**instrument_fields)  # type: ignore[arg-type]
    provider = FakeMarketDataProvider(
        quote=_paper_quote(
            exchange=instrument.exchange,
            symbol_token=instrument.symbol_token,
            trading_symbol=instrument.trading_symbol,
        )
    )
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=provider,
        bridge=bridge,
        instrument=instrument,
    )

    with pytest.raises(ToolError, match="limited to NSE EQ"):
        await FinEdAssistant().prepare_paper_order(
            _context(state),
            "buy",
            instrument.exchange,
            instrument.symbol_token,
            1,
        )

    assert provider.calls == []
    assert bridge.draft is None


@pytest.mark.asyncio
async def test_prepare_order_rejects_real_shape_bse_cash_before_quote() -> None:
    instrument = MarketInstrument(
        exchange="BSE",
        trading_symbol="RELIANCE",
        symbol_token="500325",
        series=None,
    )
    provider = FakeMarketDataProvider(
        quote=_paper_quote(
            exchange="BSE",
            symbol_token="500325",
            trading_symbol="RELIANCE",
        )
    )
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=provider,
        bridge=bridge,
        instrument=instrument,
    )

    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "BSE", "500325", 1
        )

    assert str(failure.value) == (
        "Paper fills are currently limited to NSE EQ cash equity and ETF delivery."
    )
    assert provider.calls == []
    assert bridge.draft is None


@pytest.mark.asyncio
async def test_prepare_order_rejects_unresolved_instrument_before_quote() -> None:
    provider = FakeMarketDataProvider(quote=_paper_quote())
    bridge = FakePaperTradingBridge()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        paper_trading=bridge,
    )

    with pytest.raises(ToolError, match="search_market_instruments"):
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert provider.calls == []
    assert bridge.draft is None


@pytest.mark.asyncio
async def test_prepare_order_rounds_provider_rupees_to_paise_half_up() -> None:
    now = datetime.now(UTC)
    bridge = FakePaperTradingBridge()
    quote = MarketQuote(
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        last_traded_price=Decimal("1.005"),
        close_price=Decimal("1.00"),
        provider="Angel One SmartAPI",
        exchange_time=now,
        received_time=now,
    )
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=quote),
        bridge=bridge,
    )

    await FinEdAssistant().prepare_paper_order(_context(state), "buy", "NSE", "2885", 1)

    assert bridge.draft is not None
    assert bridge.draft.price_paise == 101


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side", "quantity", "message"),
    [
        ("hold", 1, "side must be buy or sell"),
        ("BUY", 1, "side must be buy or sell"),
        ("buy", 0, "quantity must be a positive integer"),
        ("buy", True, "quantity must be a positive integer"),
    ],
)
async def test_prepare_order_rejects_invalid_side_or_quantity_before_quote(
    side: str, quantity: int, message: str
) -> None:
    provider = FakeMarketDataProvider(quote=_paper_quote())
    state = _paper_state(
        provider=provider,
        bridge=FakePaperTradingBridge(),
    )

    with pytest.raises(ToolError, match=message):
        await FinEdAssistant().prepare_paper_order(
            _context(state), side, "NSE", "2885", quantity
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_fno_mode_rejects_paper_order_preparation() -> None:
    state = _paper_state(
        profile=ParticipantProfile(LearningMode.FNO),
        provider=FakeMarketDataProvider(quote=_paper_quote()),
        bridge=FakePaperTradingBridge(),
    )

    with pytest.raises(ToolError, match="limited to NSE EQ") as failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert str(failure.value) == (
        "Paper fills are currently limited to NSE EQ cash equity and ETF delivery."
    )


@pytest.mark.asyncio
async def test_prepare_order_rejects_quote_that_cannot_reach_browser_unexpired() -> (
    None
):
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=_paper_quote(age_seconds=31)),
        bridge=bridge,
    )

    with pytest.raises(ToolError, match="fresh quote"):
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert bridge.draft is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", [UnsupportedScheduleError, ScheduleConfigurationError]
)
async def test_prepare_order_marks_charges_unavailable_only_for_documented_schedule_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    def unavailable(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise error_type("private charge schedule detail")

    monkeypatch.setattr("fined.agent.calculate_delivery_fill", unavailable)
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=_paper_quote()),
        bridge=bridge,
    )

    result = await FinEdAssistant().prepare_paper_order(
        _context(state), "sell", "NSE", "2885", 2
    )

    assert result["filled"] is False
    assert bridge.draft is not None
    assert bridge.draft.charge_status == "unavailable"
    assert bridge.draft.charge_paise is None
    assert bridge.draft.cash_effect_paise is None


@pytest.mark.asyncio
async def test_prepare_order_sanitizes_unexpected_charge_failure_without_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("private charge implementation detail")

    monkeypatch.setattr("fined.agent.calculate_delivery_fill", fail)
    bridge = FakePaperTradingBridge()
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=_paper_quote()),
        bridge=bridge,
    )

    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert str(failure.value) == "Paper order charges could not be calculated safely."
    assert "private" not in str(failure.value)
    assert bridge.draft is None
    assert state.pending_paper_drafts == {}


@pytest.mark.asyncio
async def test_prepare_order_uses_indian_market_date_for_same_day_charges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 8, 8, 20, 0, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            del cls, tz
            return fixed_now

    captured_trade_dates: list[date] = []

    def calculate(fill: object) -> object:
        captured_trade_dates.append(fill.trade_date)  # type: ignore[attr-defined]
        return SimpleNamespace(total_charges=Decimal("1.23"))

    monkeypatch.setattr("fined.agent.datetime", FixedDateTime)
    monkeypatch.setattr("fined.agent.calculate_delivery_fill", calculate)
    quote = MarketQuote(
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        last_traded_price=Decimal("2500.50"),
        close_price=Decimal("2490.00"),
        provider="Angel One SmartAPI",
        exchange_time=fixed_now,
        received_time=fixed_now,
    )
    state = _paper_state(
        provider=FakeMarketDataProvider(quote=quote),
        bridge=FakePaperTradingBridge(),
    )

    await FinEdAssistant().prepare_paper_order(_context(state), "buy", "NSE", "2885", 1)

    assert captured_trade_dates == [date(2026, 8, 9)]


@pytest.mark.asyncio
async def test_paper_tools_sanitize_bridge_and_provider_failures() -> None:
    bridge = FakePaperTradingBridge(fail=True)
    state = _paper_state(provider=FakeMarketDataProvider(), bridge=bridge)

    with pytest.raises(ToolError) as bridge_failure:
        await FinEdAssistant().open_paper_trading_dashboard(_context(state))
    with pytest.raises(ToolError) as provider_failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert str(bridge_failure.value) == "Paper trading is unavailable right now."
    assert str(provider_failure.value) == "Live market data is temporarily unavailable."
    assert state.pending_paper_drafts == {}


@pytest.mark.asyncio
async def test_real_unconfigured_market_provider_blocks_paper_order_before_browser() -> (
    None
):
    bridge = FakePaperTradingBridge()
    instrument = _paper_instrument()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=create_market_data_provider(environment={}),
        paper_trading=bridge,
        resolved_market_instruments={
            (instrument.exchange, instrument.symbol_token): instrument
        },
    )

    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().prepare_paper_order(
            _context(state), "buy", "NSE", "2885", 1
        )

    assert str(failure.value) == "Live market data is temporarily unavailable."
    assert state.pending_paper_drafts == {}
    assert bridge.prepare_calls == 0
    assert bridge.draft is None


@pytest.mark.asyncio
async def test_paper_portfolio_summary_is_virtual_and_not_an_order() -> None:
    bridge = FakePaperTradingBridge()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        paper_trading=bridge,
    )

    result = await FinEdAssistant().get_paper_portfolio_summary(_context(state))

    assert bridge.summary_calls == 1
    assert result == {
        "cash_paise": 9_500_000,
        "holdings_cost_basis_paise": 500_000,
        "cash_plus_cost_basis_paise": 10_000_000,
        "valuation_basis": "historical_cost_basis",
        "live_value_available": False,
        "notice": (
            "Holdings are shown at historical cost basis; live portfolio value "
            "is unavailable."
        ),
        "paper": True,
        "is_order": False,
    }


@pytest.mark.asyncio
async def test_quote_tool_returns_timestamped_read_only_provenance() -> None:
    provider = FakeMarketDataProvider(
        MarketQuote(
            exchange="NSE",
            symbol_token="3045",
            trading_symbol="SBIN-EQ",
            last_traded_price=Decimal("812.35"),
            close_price=Decimal("808.10"),
            provider="Angel One SmartAPI",
            exchange_time=datetime(2026, 8, 8, 3, 30, tzinfo=UTC),
            received_time=datetime(2026, 8, 8, 3, 30, 1, tzinfo=UTC),
        )
    )
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
    )

    result = await FinEdAssistant().get_market_quote(
        context=_context(state), exchange="NSE", symbol_token="3045"
    )

    assert provider.calls == [QuoteRequest("NSE", "3045")]
    assert result["last_traded_price"] == "812.35"
    assert result["provider"] == "Angel One SmartAPI"
    assert result["is_order"] is False
    assert "education" in str(result["message"]).casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exchange", "symbol_token", "message"),
    [
        ("NFO", "3045", "NSE or BSE"),
        ("NSE", "SBIN", "symbol token"),
    ],
)
async def test_quote_tool_rejects_untrusted_instrument_inputs(
    exchange: str, symbol_token: str, message: str
) -> None:
    provider = FakeMarketDataProvider()
    state = SessionState(
        profile=ParticipantProfile(),
        retriever=FakeRetriever([]),
        market_data=provider,
    )

    with pytest.raises(ToolError, match=message):
        await FinEdAssistant().get_market_quote(
            context=_context(state), exchange=exchange, symbol_token=symbol_token
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_quote_tool_sanitizes_provider_failure() -> None:
    state = SessionState(
        profile=ParticipantProfile(),
        retriever=FakeRetriever([]),
        market_data=FakeMarketDataProvider(),
    )

    with pytest.raises(ToolError) as failure:
        await FinEdAssistant().get_market_quote(
            context=_context(state), exchange="NSE", symbol_token="3045"
        )

    assert str(failure.value) == "Live market data is temporarily unavailable."
    assert "provider detail" not in str(failure.value)


@pytest.mark.asyncio
async def test_historical_return_tool_uses_resolved_instrument_and_provider_prices() -> (
    None
):
    # Catches guessed tokens, fractional units or provider-free historical arithmetic.
    instrument = _paper_instrument()
    provider = FakeMarketDataProvider(
        historical_prices=HistoricalPricePair(
            entry=HistoricalClose(date(2024, 1, 8), Decimal("100")),
            valuation=HistoricalClose(date(2026, 8, 7), Decimal("125")),
            provider="Angel One SmartAPI",
        )
    )
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        resolved_market_instruments={
            (instrument.exchange, instrument.symbol_token): instrument
        },
    )

    result = await FinEdAssistant().calculate_historical_return(
        context=_context(state),
        exchange="NSE",
        symbol_token="2885",
        purchase_date="2024-01-06",
        valuation_date="2026-08-07",
        investment_amount="10000",
    )

    assert provider.historical_calls == [
        HistoricalPriceRequest("NSE", "2885", date(2024, 1, 6), date(2026, 8, 7))
    ]
    assert result["trading_symbol"] == "RELIANCE-EQ"
    assert result["requested_purchase_date"] == "2024-01-06"
    assert result["requested_valuation_date"] == "2026-08-07"
    assert result["entry_date"] == "2024-01-08"
    assert result["units"] == 100
    assert result["final_value"] == "12500.00"
    assert result["percentage_return"] == "25.00"
    assert result["adjusted_for_corporate_actions"] is False
    assert result["is_forecast"] is False
    assert result["is_recommendation"] is False
    assert result["is_order"] is False


@pytest.mark.asyncio
async def test_historical_return_tool_requires_search_and_rejects_future_dates() -> (
    None
):
    # Catches arbitrary token use and future data requests reaching the provider.
    provider = FakeMarketDataProvider()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
    )

    with pytest.raises(ToolError, match="search_market_instruments"):
        await FinEdAssistant().calculate_historical_return(
            _context(state), "NSE", "2885", "2024-01-06", "2026-08-07", "10000"
        )
    state.resolved_market_instruments[("NSE", "2885")] = _paper_instrument()
    with pytest.raises(ToolError, match="future"):
        await FinEdAssistant().calculate_historical_return(
            _context(state), "NSE", "2885", "2024-01-06", "2099-01-01", "10000"
        )

    assert provider.historical_calls == []


@pytest.mark.asyncio
async def test_historical_return_tool_sanitizes_provider_and_amount_failures() -> None:
    # Catches raw provider details or Decimal failures escaping into model context.
    instrument = _paper_instrument()
    provider = FakeMarketDataProvider()
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
        market_data=provider,
        resolved_market_instruments={
            (instrument.exchange, instrument.symbol_token): instrument
        },
    )
    assistant = FinEdAssistant()

    with pytest.raises(ToolError) as provider_failure:
        await assistant.calculate_historical_return(
            _context(state), "NSE", "2885", "2024-01-06", "2026-08-07", "10000"
        )
    with pytest.raises(ToolError, match="supported range") as amount_failure:
        await assistant.calculate_historical_return(
            _context(state),
            "NSE",
            "2885",
            "2024-01-06",
            "2026-08-07",
            "100000000.01",
        )

    assert str(provider_failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert "provider detail" not in str(provider_failure.value)
    assert "Traceback" not in str(amount_failure.value)


@pytest.mark.asyncio
async def test_search_tool_returns_json_provenance_and_uses_session_mode() -> None:
    # Catches dropping provenance, accepting guessed authority, or bypassing session mode.
    hit = SearchHit(
        source_id="sebi_etf",
        authority="regulator",
        broker=None,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        title="SEBI ETF guide",
        url="https://example.test/sebi-etf",
        publisher="SEBI",
        verified_on=date(2026, 8, 6),
        applicability="market-wide; from 2026-01-01",
        passage="ETF units exchange par trade hote hain; market risk applies.",
        score=0.031,
        confidence="high",
    )
    retriever = FakeRetriever([hit])
    state = SessionState(
        profile=ParticipantProfile(LearningMode.ETFS), retriever=retriever
    )

    result = await FinEdAssistant().search_market_knowledge(
        context=_context(state),
        query="ETF kya hota hai?",
        as_of_date="2026-08-06",
        broker="angelone",
    )

    assert retriever.calls == [
        {
            "query": "ETF kya hota hai?",
            "learning_mode": LearningMode.ETFS,
            "as_of_date": date(2026, 8, 6),
            "broker": "Angel One",
            "top_k": 4,
        }
    ]
    assert result == {
        "verified": True,
        "hits": [
            {
                "source_id": "sebi_etf",
                "authority": "regulator",
                "broker": None,
                "effective_from": "2026-01-01",
                "effective_to": None,
                "title": "SEBI ETF guide",
                "url": "https://example.test/sebi-etf",
                "publisher": "SEBI",
                "verified_on": "2026-08-06",
                "applicability": "market-wide; from 2026-01-01",
                "passage": "ETF units exchange par trade hote hain; market risk applies.",
                "score": 0.031,
                "confidence": "high",
                "source_link": "[SEBI ETF guide](https://example.test/sebi-etf)",
            }
        ],
    }


@pytest.mark.asyncio
async def test_search_tool_abstains_when_retrieval_has_no_evidence() -> None:
    # Catches empty retrieval being presented as verified or permission to guess.
    retriever = FakeRetriever([])
    state = SessionState(
        profile=ParticipantProfile(LearningMode.GOLD), retriever=retriever
    )

    result = await FinEdAssistant().search_market_knowledge(
        context=_context(state), query="unsupported claim"
    )

    assert result["verified"] is False
    assert result["hits"] == []
    assert "do not guess" in str(result["message"]).casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"query": "   "}, "market question"),
        ({"query": "₹" * 1366}, "4096"),
        ({"query": "ETF", "as_of_date": "2026-8-6"}, "YYYY-MM-DD"),
        ({"query": "ETF", "as_of_date": "2026-02-30"}, "YYYY-MM-DD"),
        ({"query": "ETF", "broker": "Other Broker"}, "Angel One"),
    ],
)
async def test_search_tool_rejects_unsafe_user_input_with_short_tool_errors(
    kwargs: dict[str, object], message: str
) -> None:
    # Catches unbounded queries, permissive dates/brokers, and raw validation failures.
    retriever = FakeRetriever([])
    state = SessionState(
        profile=ParticipantProfile(LearningMode.GENERAL), retriever=retriever
    )

    with pytest.raises(ToolError, match=message) as failure:
        await FinEdAssistant().search_market_knowledge(  # type: ignore[arg-type]
            context=_context(state), **kwargs
        )

    assert "Traceback" not in str(failure.value)
    assert retriever.calls == []


@pytest.mark.asyncio
async def test_calculator_tool_returns_current_six_rupee_delivery_estimate() -> None:
    # Catches LLM-side fee arithmetic or loss of calculator provenance/status.
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
    )

    result = await FinEdAssistant().calculate_angel_one_trade_cost(
        context=_context(state),
        trade_date="2026-08-06",
        exchange="NSE",
        quantity=1,
        buy_price="6",
        sell_price="6",
        brokerage_promotion_applies=False,
    )

    assert result["product"] == "equity_delivery"
    assert result["estimate_status"] == "illustrative_estimate"
    assert result["total_charges"] == "35.41"
    assert result["net_pnl"] == "-35.41"
    assert result["applicability"] == {
        "broker": "Angel One",
        "product": "equity_delivery",
        "trade_date": "2026-08-06",
        "exchange": "NSE",
    }
    assert result["source_links"]
    assert all(
        link.startswith("[") and "](https://" in link for link in result["source_links"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"trade_date": "2026-8-6"}, "YYYY-MM-DD"),
        ({"exchange": "MCX"}, "NSE or BSE"),
        ({"quantity": True}, "quantity"),
        ({"buy_price": "provider-secret-value"}, "buy_price"),
        ({"sell_price": "NaN"}, "sell_price"),
        ({"demat_debit": 1}, "demat_debit"),
        ({"brokerage_promotion_applies": "yes"}, "promotion"),
        ({"executed_buy_orders": 0}, "executed_buy_orders"),
        ({"executed_sell_orders": False}, "executed_sell_orders"),
        ({"demat_debits": -1}, "demat_debits"),
        ({"exchange": "BSE", "bse_group": None}, "BSE scrip group"),
        ({"exchange": "BSE", "bse_group": "NOT-A-GROUP"}, "BSE scrip group"),
    ],
)
async def test_calculator_tool_rejects_invalid_inputs_without_echoing_them(
    changes: dict[str, object], message: str
) -> None:
    # Catches bool-as-int, non-finite Decimal, unsupported product data, and secret echo.
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
    )
    kwargs: dict[str, object] = {
        "trade_date": "2026-08-06",
        "exchange": "NSE",
        "quantity": 1,
        "buy_price": "6",
        "sell_price": "6",
    }
    kwargs.update(changes)

    with pytest.raises(ToolError, match=message) as failure:
        await FinEdAssistant().calculate_angel_one_trade_cost(  # type: ignore[arg-type]
            context=_context(state), **kwargs
        )

    text = str(failure.value)
    assert "Traceback" not in text
    assert "provider-secret-value" not in text


@pytest.mark.asyncio
async def test_calculator_tool_turns_unsupported_schedule_into_safe_tool_error() -> (
    None
):
    # Catches raw schedule exceptions escaping into the model-visible tool result.
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
    )

    with pytest.raises(ToolError, match="verified Angel One schedule") as failure:
        await FinEdAssistant().calculate_angel_one_trade_cost(
            context=_context(state),
            trade_date="2026-02-28",
            exchange="NSE",
            quantity=1,
            buy_price="6",
            sell_price="6",
        )

    assert "2026-02-28" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"buy_price": "1e999999"},
        {"buy_price": "1e-999999"},
        {"quantity": 10**1000},
    ],
)
async def test_calculator_tool_translates_extreme_decimal_arithmetic_errors(
    changes: dict[str, object],
) -> None:
    # Catches raw Decimal exceptions escaping for finite positive user inputs.
    state = SessionState(
        profile=ParticipantProfile(LearningMode.STOCKS),
        retriever=FakeRetriever([]),
    )
    kwargs: dict[str, object] = {
        "trade_date": "2026-08-06",
        "exchange": "NSE",
        "quantity": 1,
        "buy_price": "6",
        "sell_price": "6",
    }
    kwargs.update(changes)

    with pytest.raises(ToolError, match="supported calculation range") as failure:
        await FinEdAssistant().calculate_angel_one_trade_cost(  # type: ignore[arg-type]
            context=_context(state), **kwargs
        )

    assert "Traceback" not in str(failure.value)


@pytest.mark.asyncio
async def test_fno_session_cannot_reach_the_delivery_calculator() -> None:
    # Catches prompt bypass that routes an F&O-mode session into delivery arithmetic.
    state = SessionState(
        profile=ParticipantProfile(LearningMode.FNO),
        retriever=FakeRetriever([]),
    )

    with pytest.raises(ToolError, match="F&O mode") as failure:
        await FinEdAssistant().calculate_angel_one_trade_cost(
            context=_context(state),
            trade_date="2026-02-28",
            exchange="NSE",
            quantity=1,
            buy_price="6",
            sell_price="6",
        )

    assert "educational payoff examples only" in str(failure.value)
    assert "simulation only" not in str(failure.value)


@pytest.mark.asyncio
async def test_memory_tools_lookup_and_save_safe_learning_context(tmp_path) -> None:
    # Catches tools using prompt state instead of the caller-scoped persistent store.
    store = SQLiteCallerMemoryStore(tmp_path / "memory.sqlite3")
    state = SessionState(
        profile=ParticipantProfile(LearningMode.ETFS),
        retriever=FakeRetriever([]),
        caller_id="voice_assistant_user_learner-7",
        memory_store=store,
    )
    assistant = FinEdAssistant()

    first_lookup = await assistant.lookup_caller_memory(context=_context(state))
    saved = await assistant.save_caller_memory(
        context=_context(state),
        name="Himanshu",
        language_preference="bilingual",
        experience_level="beginner",
        learning_goal="understand ETFs before paper practice",
        consent_confirmed=True,
    )
    second_lookup = await assistant.lookup_caller_memory(context=_context(state))

    assert first_lookup == {
        "found": False,
        "message": "No saved caller memory was found.",
    }
    assert saved["saved"] is True
    assert saved["name"] == "Himanshu"
    assert saved["facts"] == {
        "experience_level": "beginner",
        "learning_goal": "understand ETFs before paper practice",
    }
    assert second_lookup["found"] is True
    assert second_lookup["name"] == "Himanshu"
    assert second_lookup["facts"] == saved["facts"]
    assert "caller_id" not in second_lookup


@pytest.mark.asyncio
async def test_memory_tool_refuses_save_without_current_explicit_consent(
    tmp_path,
) -> None:
    # Catches the model calling the write tool before a clear yes from the caller.
    store = SQLiteCallerMemoryStore(tmp_path / "memory.sqlite3")
    state = SessionState(
        profile=ParticipantProfile(),
        retriever=FakeRetriever([]),
        caller_id="voice_assistant_user_learner-7",
        memory_store=store,
    )

    with pytest.raises(ToolError, match="explicit yes"):
        await FinEdAssistant().save_caller_memory(
            context=_context(state),
            name="Himanshu",
            language_preference="english",
            experience_level="beginner",
            learning_goal="learn about SIPs",
            consent_confirmed=False,
        )

    assert store.lookup("voice_assistant_user_learner-7") is None


@pytest.mark.asyncio
async def test_forget_tool_requires_consent_then_removes_memory(tmp_path) -> None:
    # Catches a forget request deleting data without explicit confirmation.
    store = SQLiteCallerMemoryStore(tmp_path / "memory.sqlite3")
    state = SessionState(
        profile=ParticipantProfile(),
        retriever=FakeRetriever([]),
        caller_id="voice_assistant_user_learner-7",
        memory_store=store,
    )
    assistant = FinEdAssistant()
    await assistant.save_caller_memory(
        context=_context(state),
        name="Himanshu",
        language_preference="english",
        experience_level="beginner",
        learning_goal="learn about SIPs",
        consent_confirmed=True,
    )

    with pytest.raises(ToolError, match="explicit yes"):
        await assistant.forget_caller_memory(
            context=_context(state), consent_confirmed=False
        )
    assert store.lookup("voice_assistant_user_learner-7") is not None

    result = await assistant.forget_caller_memory(
        context=_context(state), consent_confirmed=True
    )

    assert result == {"forgotten": True, "message": "Saved caller memory was deleted."}
    assert store.lookup("voice_assistant_user_learner-7") is None


@pytest.mark.asyncio
async def test_default_memory_store_fails_closed_when_forgetting() -> None:
    state = SessionState(
        profile=ParticipantProfile(),
        retriever=FakeRetriever([]),
        caller_id="voice_assistant_user_learner-7",
    )
    assert hasattr(state.memory_store, "forget")

    with pytest.raises(ToolError, match="Caller memory is temporarily unavailable"):
        await FinEdAssistant().forget_caller_memory(
            context=_context(state), consent_confirmed=True
        )
