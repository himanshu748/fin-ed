from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
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
from fined.knowledge.index import SearchHit
from fined.market_data.models import MarketQuote, QuoteRequest
from fined.market_data.provider import MarketDataUnavailableError
from fined.modes import LearningMode


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

    async def get_quote(self, request: QuoteRequest) -> MarketQuote:
        self.calls.append(request)
        if self.quote is None:
            raise MarketDataUnavailableError("provider detail must stay hidden")
        return self.quote


def _context(state: SessionState) -> RunContext[SessionState]:
    return cast(RunContext[SessionState], SimpleNamespace(userdata=state))


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
        "education and simulation only",
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
        "never execute a trade",
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
    assert "education and simulation" in fno.casefold()


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

    with pytest.raises(ToolError, match="F&O mode"):
        await FinEdAssistant().calculate_angel_one_trade_cost(
            context=_context(state),
            trade_date="2026-02-28",
            exchange="NSE",
            quantity=1,
            buy_price="6",
            sell_price="6",
        )
