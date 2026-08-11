from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livekit import rtc

import agent as entrypoint
from fined.knowledge.ingest import BuildError
from fined.market_data.models import MarketQuote
from fined.market_data.provider import MarketDataUnavailableError
from fined.memory import CallerMemory
from fined.modes import LearningMode
from fined.outbound import (
    OUTBOUND_DIAL_TIMEOUT_SECONDS,
    PAPER_PRACTICE_REMINDER,
    build_outbound_greeting,
    build_outbound_metadata,
)
from fined.paper_trading import PaperOrderDraft


class LifecycleAbort(BaseException):
    """Sentinel proving BaseException cleanup does not suppress the original failure."""


def test_development_worker_keeps_one_job_process_warm() -> None:
    """Prevent the first caller from waiting for a cold Python job process."""
    assert entrypoint.server._num_idle_processes == 1


class FakeAsyncClient:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.close_attempts = 0

    async def aclose(self) -> None:
        self.close_attempts += 1
        self.events.append("close")


class FakeEmbeddingClient:
    def __init__(self, events: list[str]) -> None:
        self.aio = FakeAsyncClient(events)


class FakeUsageCollector:
    def __init__(self, fail_at: str | None) -> None:
        self.fail_at = fail_at

    def collect(self, metric: object) -> None:
        del metric

    def get_summary(self) -> dict[str, int]:
        if self.fail_at == "usage_summary":
            raise LifecycleAbort("usage_summary")
        return {"requests": 0}


class FakeSession:
    def __init__(self, events: list[str], fail_at: str | None) -> None:
        self.events = events
        self.fail_at = fail_at
        self.userdata: object | None = None
        self.kwargs: dict[str, object] = {}
        self.spoken: list[str] = []
        self.generated_replies: list[dict[str, object]] = []
        self.callbacks: dict[str, list[Any]] = {}

    def on(self, event_name: str):
        assert event_name in {"metrics_collected", "error"}
        registration_name = (
            "metrics_registration"
            if event_name == "metrics_collected"
            else "error_registration"
        )
        self.events.append(registration_name)
        if self.fail_at == registration_name:
            raise LifecycleAbort(registration_name)

        def register(callback: Any) -> Any:
            self.callbacks.setdefault(event_name, []).append(callback)
            return callback

        return register

    async def start(self, **kwargs: object) -> None:
        self.events.append("start")
        if self.fail_at == "start":
            raise LifecycleAbort("start")
        assert kwargs["room"] is not None

    async def say(self, greeting: str) -> None:
        self.events.append("say")
        self.spoken.append(greeting)
        if self.fail_at == "say":
            raise LifecycleAbort("say")

    async def generate_reply(self, **kwargs: object) -> None:
        self.events.append("generate_reply")
        self.generated_replies.append(kwargs)
        self.spoken.append("generated caller-memory greeting")
        if self.fail_at == "generate_reply":
            raise LifecycleAbort("generate_reply")


class FakeLocalParticipant:
    def __init__(self, events: list[str], fail_at: str | None) -> None:
        self.events = events
        self.fail_at = fail_at
        self.rpc_methods: dict[str, Any] = {}
        self.outbound_rpc_calls: list[dict[str, object]] = []

    def register_rpc_method(self, method_name: str, handler: Any) -> Any:
        self.events.append("rpc_registration")
        if self.fail_at == "rpc_registration":
            raise LifecycleAbort("rpc_registration")
        self.rpc_methods[method_name] = handler
        return handler

    def unregister_rpc_method(self, method_name: str) -> None:
        self.events.append("rpc_unregistration")
        self.rpc_methods.pop(method_name, None)

    async def perform_rpc(self, **kwargs: object) -> str:
        self.outbound_rpc_calls.append(kwargs)
        return '{"version":1,"paper":true,"opened":true}'


class FakeRoomService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.removals: list[object] = []

    async def remove_participant(self, request: object) -> None:
        self.events.append("remove_participant")
        self.removals.append(request)


class FakeContext:
    def __init__(self, events: list[str], fail_at: str | None) -> None:
        self.events = events
        self.fail_at = fail_at
        self.local_participant = FakeLocalParticipant(events, fail_at)
        self.room = SimpleNamespace(
            name="test-room", local_participant=self.local_participant
        )
        self.room_service = FakeRoomService(events)
        self.api = SimpleNamespace(room=self.room_service)
        self.proc = SimpleNamespace(userdata={"vad": object()})
        self.log_context_fields: dict[str, str] = {}
        self.shutdown_callbacks: list[Any] = []
        self.shutdown_reasons: list[str] = []

    async def connect(self) -> None:
        self.events.append("connect")

    async def wait_for_participant(self) -> SimpleNamespace:
        self.events.append("participant")
        return SimpleNamespace(
            identity="learner-1", metadata='{"learning_mode":"stocks"}'
        )

    def add_shutdown_callback(self, callback: Any) -> None:
        self.events.append("shutdown_registration")
        self.shutdown_callbacks.append(callback)
        if self.fail_at == "shutdown_registration":
            raise LifecycleAbort("shutdown_registration")

    def shutdown(self, reason: str) -> None:
        self.events.append("shutdown")
        self.shutdown_reasons.append(reason)


@dataclass
class LifecycleHarness:
    events: list[str]
    client: FakeEmbeddingClient
    session: FakeSession
    context: FakeContext
    llm: object
    llm_kwargs: dict[str, object]
    stt_kwargs: dict[str, object]
    tts_kwargs: dict[str, object]
    turn_detection_kwargs: dict[str, object]


def _install_lifecycle_fakes(
    monkeypatch: pytest.MonkeyPatch,
    fail_at: str | None,
    knowledge_directory: Path,
    *,
    knowledge_available: bool = True,
) -> LifecycleHarness:
    events: list[str] = []
    client = FakeEmbeddingClient(events)
    session = FakeSession(events, fail_at)
    context = FakeContext(events, fail_at)
    llm = object()
    llm_kwargs: dict[str, object] = {}
    stt_kwargs: dict[str, object] = {}
    tts_kwargs: dict[str, object] = {}
    turn_detection_kwargs: dict[str, object] = {}

    knowledge_directory.mkdir(parents=True)
    if knowledge_available:
        build = knowledge_directory / "builds" / "build-20260806T000000000000Z"
        build.mkdir(parents=True)
        (knowledge_directory / "current").symlink_to(
            build.relative_to(knowledge_directory)
        )

    def stage(name: str, value: object):
        def factory(*args: object, **kwargs: object) -> object:
            del args, kwargs
            events.append(name)
            if fail_at == name:
                raise LifecycleAbort(name)
            return value

        return factory

    def load_environment(path: str) -> None:
        assert path.endswith(".env.local")
        events.append("dotenv")

    def client_factory() -> FakeEmbeddingClient:
        events.append("client")
        return client

    def log_info(message: str, *args: object) -> None:
        del message, args
        if fail_at == "usage_logger":
            raise LifecycleAbort("usage_logger")

    def llm_factory(*args: object, **kwargs: object) -> object:
        assert not args
        events.append("llm")
        if fail_at == "llm":
            raise LifecycleAbort("llm")
        llm_kwargs.update(kwargs)
        return llm

    def stt_factory(*args: object, **kwargs: object) -> object:
        assert not args
        events.append("provider")
        if fail_at == "provider":
            raise LifecycleAbort("provider")
        stt_kwargs.update(kwargs)
        return object()

    def tts_factory(*args: object, **kwargs: object) -> object:
        assert not args
        events.append("tts")
        if fail_at == "tts":
            raise LifecycleAbort("tts")
        tts_kwargs.update(kwargs)
        return object()

    def turn_detection_factory(*args: object, **kwargs: object) -> object:
        assert not args
        events.append("turn_detection")
        if fail_at == "turn_detection":
            raise LifecycleAbort("turn_detection")
        turn_detection_kwargs.update(kwargs)
        return object()

    class SessionFactory:
        @classmethod
        def __class_getitem__(cls, item: object) -> type[SessionFactory]:
            del item
            return cls

        def __new__(cls, **kwargs: object) -> FakeSession:
            del cls
            events.append("session")
            if fail_at == "session":
                raise LifecycleAbort("session")
            session.userdata = kwargs["userdata"]
            session.kwargs = kwargs
            return session

    monkeypatch.setattr(entrypoint, "load_dotenv", load_environment)
    monkeypatch.setattr(entrypoint, "KNOWLEDGE_DIRECTORY", knowledge_directory)
    monkeypatch.setattr(
        entrypoint,
        "MEMORY_DATABASE_PATH",
        knowledge_directory.parent / "memory" / "fined.sqlite3",
    )
    monkeypatch.setattr(entrypoint.logger, "info", log_info)
    monkeypatch.setattr(entrypoint.genai, "Client", client_factory)
    monkeypatch.setattr(entrypoint, "GeminiEmbedder", stage("embedder", object()))
    monkeypatch.setattr(entrypoint.KnowledgeIndex, "load", stage("index", object()))
    monkeypatch.setattr(entrypoint.deepgram, "STT", stt_factory)
    monkeypatch.setattr(entrypoint.google, "LLM", llm_factory)
    monkeypatch.setattr(
        entrypoint.tokenize.basic, "SentenceTokenizer", stage("tokenizer", object())
    )
    monkeypatch.setattr(entrypoint.murf, "TTS", tts_factory)
    monkeypatch.setattr(entrypoint.inference, "TurnDetector", turn_detection_factory)
    monkeypatch.setattr(entrypoint, "AgentSession", SessionFactory)
    monkeypatch.setattr(
        entrypoint.metrics,
        "UsageCollector",
        stage("usage", FakeUsageCollector(fail_at)),
    )
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    return LifecycleHarness(
        events,
        client,
        session,
        context,
        llm,
        llm_kwargs,
        stt_kwargs,
        tts_kwargs,
        turn_detection_kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fail_at",
    [
        "embedder",
        "index",
        "provider",
        "llm",
        "session",
        "usage",
        "metrics_registration",
        "error_registration",
        "rpc_registration",
        "shutdown_registration",
        "start",
        "say",
    ],
)
async def test_every_post_client_failure_closes_once_and_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fail_at: str
) -> None:
    # Catches setup stages escaping the cleanup boundary or swallowing BaseException.
    harness = _install_lifecycle_fakes(monkeypatch, fail_at, tmp_path / "generated")

    with pytest.raises(LifecycleAbort, match=fail_at):
        await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    assert harness.client.aio.close_attempts == 1
    expected_unregistrations = 2 * int(
        fail_at in {"shutdown_registration", "start", "say"}
    )
    assert harness.events.count("rpc_unregistration") == expected_unregistrations
    for callback in harness.context.shutdown_callbacks:
        await callback("later shutdown")
    assert harness.client.aio.close_attempts == 1
    assert harness.events.count("rpc_unregistration") == expected_unregistrations


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", ["usage_summary", "usage_logger"])
async def test_shutdown_failure_still_closes_once_and_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fail_at: str
) -> None:
    # Catches usage reporting failures that bypass successful-session cleanup.
    harness = _install_lifecycle_fakes(monkeypatch, fail_at, tmp_path / "generated")
    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    callback = harness.context.shutdown_callbacks[0]
    with pytest.raises(LifecycleAbort, match=fail_at):
        await callback("normal shutdown")
    assert harness.client.aio.close_attempts == 1
    assert harness.events.count("rpc_unregistration") == 2

    with pytest.raises(LifecycleAbort, match=fail_at):
        await callback("duplicate shutdown")
    assert harness.client.aio.close_attempts == 1
    assert harness.events.count("rpc_unregistration") == 2


@pytest.mark.asyncio
async def test_success_defers_one_close_to_idempotent_shutdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Catches eager success cleanup, ordering regressions, and duplicate shutdown closes.
    harness = _install_lifecycle_fakes(monkeypatch, None, tmp_path / "generated")

    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    assert harness.events == [
        "connect",
        "participant",
        "dotenv",
        "client",
        "embedder",
        "index",
        "provider",
        "llm",
        "tokenizer",
        "tts",
        "turn_detection",
        "session",
        "usage",
        "metrics_registration",
        "error_registration",
        "rpc_registration",
        "rpc_registration",
        "shutdown_registration",
        "start",
        "say",
    ]
    assert harness.client.aio.close_attempts == 0
    assert harness.events.count("rpc_registration") == 2
    assert harness.events.count("rpc_unregistration") == 0
    assert len(harness.context.shutdown_callbacks) == 1
    state = harness.session.userdata
    assert state is not None
    assert state.profile.learning_mode is LearningMode.STOCKS  # type: ignore[union-attr]
    assert state.caller_id == "learner-1"  # type: ignore[union-attr]
    assert harness.session.generated_replies == []
    assert harness.session.spoken == [
        "Hello, I'm FinEd Saathi, your Indian markets learning companion. "
        "I can help you learn about Stocks in English, Hindi, or both. "
        "I provide education, not investment advice. "
        "What would you like to understand today?"
    ]
    assert state.paper_trading is not None  # type: ignore[union-attr]
    dashboard_ack = await state.paper_trading.open_dashboard()  # type: ignore[union-attr]
    assert dashboard_ack.opened is True
    assert (
        harness.context.local_participant.outbound_rpc_calls[0]["destination_identity"]
        == "learner-1"
    )
    assert harness.llm_kwargs == {
        "model": "gemini-3.5-flash-lite",
        "thinking_config": {"thinking_level": "minimal"},
        "max_output_tokens": 320,
    }
    assert harness.stt_kwargs == {
        "model": "nova-3",
        "language": "multi",
        "endpointing_ms": 100,
    }
    assert harness.tts_kwargs["voice"] == "Nikhil"
    assert harness.tts_kwargs["style"] == "Conversational"
    assert harness.tts_kwargs["model"] == "falcon-2"
    assert harness.tts_kwargs["locale"] == "en-IN"
    assert harness.turn_detection_kwargs == {"version": "v1-mini"}
    assert harness.session.kwargs["llm"] is harness.llm
    assert "conn_options" not in harness.session.kwargs

    callback = harness.context.shutdown_callbacks[0]
    await callback("normal shutdown")
    await callback("duplicate shutdown")

    assert harness.client.aio.close_attempts == 1
    assert harness.events.count("rpc_unregistration") == 2
    assert entrypoint.PAPER_ORDER_RESULT_METHOD not in (
        harness.context.local_participant.rpc_methods
    )
    assert entrypoint.PAPER_HOLDING_QUOTES_METHOD not in (
        harness.context.local_participant.rpc_methods
    )


@pytest.mark.asyncio
async def test_outbound_dispatch_uses_disclosure_and_call_scoped_paper_sandbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Catches an outbound reminder inheriting browser state or lacking paper practice.
    harness = _install_lifecycle_fakes(monkeypatch, None, tmp_path / "generated")
    harness.context.job = SimpleNamespace(  # type: ignore[attr-defined]
        metadata=build_outbound_metadata(PAPER_PRACTICE_REMINDER)
    )

    def memory_lookup_should_not_run(self: object, caller_id: str) -> object:
        del self, caller_id
        raise AssertionError("outbound reminders must not read browser memory")

    monkeypatch.setattr(
        entrypoint.SQLiteCallerMemoryStore,
        "lookup",
        memory_lookup_should_not_run,
    )

    market_provider = object()
    paper_bridge = object()
    monkeypatch.setattr(
        entrypoint, "create_market_data_provider", lambda: market_provider
    )
    monkeypatch.setattr(
        entrypoint, "CallPaperTradingBridge", lambda: paper_bridge, raising=False
    )

    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    state = harness.session.userdata
    assert state is not None
    assert state.outbound_reminder == PAPER_PRACTICE_REMINDER  # type: ignore[union-attr]
    assert state.market_data is market_provider  # type: ignore[union-attr]
    assert state.paper_trading is paper_bridge  # type: ignore[union-attr]
    assert harness.session.spoken == [build_outbound_greeting(PAPER_PRACTICE_REMINDER)]
    assert "Welcome back" not in harness.session.spoken[0]
    assert harness.session.generated_replies == []
    assert harness.events.count("rpc_registration") == 0
    assert harness.context.local_participant.rpc_methods == {}
    assert harness.context.local_participant.outbound_rpc_calls == []


def test_outbound_recipient_window_exceeds_the_bounded_sip_dial_window() -> None:
    # Catches a valid near-timeout SIP answer connecting after the agent has exited.
    assert (
        entrypoint.OUTBOUND_RECIPIENT_JOIN_TIMEOUT_SECONDS
        > OUTBOUND_DIAL_TIMEOUT_SECONDS
    )


@pytest.mark.asyncio
async def test_outbound_stop_removes_the_sip_recipient_even_when_goodbye_fails() -> (
    None
):
    # Catches a failed TTS goodbye leaving a stop-requested caller connected.
    events: list[str] = []
    session = FakeSession(events, "say")
    context = FakeContext(events, None)
    control = entrypoint._LiveKitOutboundCallControl(
        session,
        context,
        "outbound-recipient-1",
    )

    with pytest.raises(LifecycleAbort, match="say"):
        await control.end_call()

    assert context.room_service.removals[0].room == "test-room"
    assert context.room_service.removals[0].identity == "outbound-recipient-1"
    assert context.shutdown_reasons == ["outbound recipient requested stop"]


@pytest.mark.asyncio
async def test_exhausted_llm_retries_speak_one_safe_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = _install_lifecycle_fakes(monkeypatch, None, tmp_path / "generated")
    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    callback = harness.session.callbacks["error"][0]
    retrying = SimpleNamespace(
        error=SimpleNamespace(type="llm_error", recoverable=True)
    )
    exhausted = SimpleNamespace(
        error=SimpleNamespace(type="llm_error", recoverable=False)
    )

    callback(retrying)
    callback(exhausted)
    callback(exhausted)
    await asyncio.sleep(0)

    assert harness.session.spoken == [
        "Hello, I'm FinEd Saathi, your Indian markets learning companion. "
        "I can help you learn about Stocks in English, Hindi, or both. "
        "I provide education, not investment advice. "
        "What would you like to understand today?",
        "The language model is temporarily busy. Please wait a moment, then ask again.",
    ]


def test_returning_caller_greeting_uses_one_safe_learning_fact() -> None:
    memory = CallerMemory(
        caller_id="learner-1",
        name="Asha",
        language_preference="english",
        facts={
            "experience_level": "beginner",
            "learning_goal": "understand ETFs",
        },
        last_interaction=datetime(2026, 8, 8, tzinfo=UTC),
    )

    greeting = entrypoint.build_caller_greeting(
        entrypoint.ParticipantProfile(LearningMode.ETFS), memory
    )

    assert greeting == (
        "Welcome back, Asha. Your saved learning goal is understand ETFs. "
        "This is education, not investment advice. "
        "What would you like to understand today?"
    )
    assert "learner-1" not in greeting


def _pending_draft(*, expired: bool = False) -> PaperOrderDraft:
    now = datetime.now(UTC)
    quote_time = now - timedelta(seconds=31) if expired else now
    return PaperOrderDraft(
        draft_id="draft-1",
        side="buy",
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        quantity=1,
        price_paise=250_050,
        quote_provider="Angel One SmartAPI",
        quote_time=quote_time,
        expires_at=quote_time + timedelta(seconds=30),
        notional_paise=250_050,
        charge_paise=123,
        cash_effect_paise=-250_173,
        charge_status="estimated",
    )


def _paper_result_payload(**changes: object) -> str:
    fields: dict[str, object] = {
        "version": 1,
        "paper": True,
        "draft_id": "draft-1",
        "side": "buy",
        "trading_symbol": "RELIANCE-EQ",
        "quantity": 1,
        "fill_price_paise": 250_050,
        "simulated_at": datetime.now(UTC).isoformat(),
        "cash_paise": 9_749_950,
    }
    fields.update(changes)
    return json.dumps(fields)


async def _result_rpc_harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[LifecycleHarness, Any]:
    harness = _install_lifecycle_fakes(monkeypatch, None, tmp_path / "generated")
    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]
    return (
        harness,
        harness.context.local_participant.rpc_methods[
            entrypoint.PAPER_ORDER_RESULT_METHOD
        ],
    )


@pytest.mark.asyncio
async def test_holding_quote_rpc_returns_trusted_partial_quotes_without_broker_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = _install_lifecycle_fakes(monkeypatch, None, tmp_path / "generated")
    await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]
    state = harness.session.userdata

    class Quotes:
        async def get_quote(self, request: object) -> MarketQuote:
            if request.symbol_token == "1594":  # type: ignore[attr-defined]
                raise MarketDataUnavailableError("not available")
            now = datetime(2026, 8, 10, 5, 4, 54, tzinfo=UTC)
            return MarketQuote(
                exchange=request.exchange,  # type: ignore[attr-defined]
                symbol_token=request.symbol_token,  # type: ignore[attr-defined]
                trading_symbol="TCS-EQ",
                last_traded_price=Decimal("2466.605"),
                close_price=Decimal("2450"),
                provider="Angel One SmartAPI",
                exchange_time=now,
                received_time=now,
            )

    state.market_data = Quotes()  # type: ignore[union-attr]
    handler = harness.context.local_participant.rpc_methods[
        entrypoint.PAPER_HOLDING_QUOTES_METHOD
    ]
    payload = json.dumps(
        {
            "version": 1,
            "paper": True,
            "holdings": [
                {
                    "exchange": "NSE",
                    "symbol_token": "11536",
                    "trading_symbol": "TCS-EQ",
                    "quantity": 1,
                },
                {
                    "exchange": "NSE",
                    "symbol_token": "1594",
                    "trading_symbol": "INFY-EQ",
                    "quantity": 2,
                },
            ],
        }
    )

    with pytest.raises(rtc.RpcError, match="not authorized"):
        await handler(rtc.RpcInvocationData("request-1", "intruder", payload, 10.0))

    response = json.loads(
        await handler(rtc.RpcInvocationData("request-2", "learner-1", payload, 10.0))
    )

    assert response == {
        "version": 1,
        "paper": True,
        "quotes": [
            {
                "exchange": "NSE",
                "symbol_token": "11536",
                "trading_symbol": "TCS-EQ",
                "price_paise": 246_661,
                "quote_time": "2026-08-10T05:04:54+00:00",
                "provider": "Angel One SmartAPI",
            }
        ],
    }


@pytest.mark.asyncio
async def test_result_rpc_accepts_original_participant_matching_pending_draft_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness, handler = await _result_rpc_harness(monkeypatch, tmp_path)
    state = harness.session.userdata
    draft = _pending_draft()
    state.pending_paper_drafts[draft.draft_id] = draft  # type: ignore[union-attr]
    payload = _paper_result_payload()

    with pytest.raises(rtc.RpcError, match="not authorized"):
        await handler(rtc.RpcInvocationData("request-1", "intruder", payload, 5.0))

    acknowledgement = await handler(
        rtc.RpcInvocationData("request-2", "learner-1", payload, 5.0)
    )

    assert acknowledgement == '{"version":1,"paper":true,"acknowledged":true}'
    assert state.pending_paper_drafts == {}  # type: ignore[union-attr]
    assert harness.session.spoken[-1] == (
        "The browser confirmed the simulated paper result."
    )

    with pytest.raises(rtc.RpcError, match="Invalid paper result"):
        await handler(rtc.RpcInvocationData("request-3", "learner-1", payload, 5.0))
    assert len(harness.session.spoken) == 2


@pytest.mark.asyncio
async def test_result_rpc_rejects_unknown_draft_without_speaking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness, handler = await _result_rpc_harness(monkeypatch, tmp_path)

    with pytest.raises(rtc.RpcError, match="Invalid paper result"):
        await handler(
            rtc.RpcInvocationData(
                "request-1", "learner-1", _paper_result_payload(), 5.0
            )
        )

    assert len(harness.session.spoken) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"side": "sell"},
        {"trading_symbol": "OTHER-EQ"},
        {"quantity": 2},
        {"fill_price_paise": 250_051},
    ],
)
async def test_result_rpc_rejects_mismatched_pending_draft_without_consuming(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    harness, handler = await _result_rpc_harness(monkeypatch, tmp_path)
    state = harness.session.userdata
    draft = _pending_draft()
    state.pending_paper_drafts[draft.draft_id] = draft  # type: ignore[union-attr]

    with pytest.raises(rtc.RpcError, match="Invalid paper result"):
        await handler(
            rtc.RpcInvocationData(
                "request-1",
                "learner-1",
                _paper_result_payload(**changes),
                5.0,
            )
        )

    assert state.pending_paper_drafts == {"draft-1": draft}  # type: ignore[union-attr]
    assert len(harness.session.spoken) == 1


@pytest.mark.asyncio
async def test_result_rpc_rejects_expired_pending_draft_without_speaking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness, handler = await _result_rpc_harness(monkeypatch, tmp_path)
    state = harness.session.userdata
    draft = _pending_draft(expired=True)
    state.pending_paper_drafts[draft.draft_id] = draft  # type: ignore[union-attr]

    with pytest.raises(rtc.RpcError, match="Invalid paper result"):
        await handler(
            rtc.RpcInvocationData(
                "request-1", "learner-1", _paper_result_payload(), 5.0
            )
        )

    assert state.pending_paper_drafts == {"draft-1": draft}  # type: ignore[union-attr]
    assert len(harness.session.spoken) == 1


@pytest.mark.asyncio
async def test_result_rpc_rejects_malformed_payload_without_speaking_private_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness, handler = await _result_rpc_harness(monkeypatch, tmp_path)

    with pytest.raises(rtc.RpcError) as failure:
        await handler(
            rtc.RpcInvocationData(
                "request-1", "learner-1", '{"access_token":"secret"}', 5.0
            )
        )

    assert str(failure.value) == "Invalid paper result."
    assert "secret" not in str(failure.value)
    assert len(harness.session.spoken) == 1


@pytest.mark.asyncio
async def test_unavailable_retriever_always_returns_no_evidence() -> None:
    retriever = entrypoint.UnavailableKnowledgeRetriever()

    hits = await retriever.search(
        "Angel One delivery charges",
        LearningMode.STOCKS,
        as_of_date=date(2026, 8, 6),
        broker="Angel One",
        top_k=100,
    )

    assert hits == []


def test_absent_current_selects_unavailable_retriever_with_fixed_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    directory = tmp_path / "generated"
    embedder = object()

    def unexpected_load(*args: object, **kwargs: object) -> object:
        del args, kwargs
        pytest.fail("KnowledgeIndex.load must not run without a current pointer")

    monkeypatch.setattr(entrypoint.KnowledgeIndex, "load", unexpected_load)

    with caplog.at_level(logging.WARNING, logger="agent"):
        retriever = entrypoint._load_knowledge_retriever(directory, embedder)

    assert isinstance(retriever, entrypoint.UnavailableKnowledgeRetriever)
    records = [record for record in caplog.records if record.name == "agent"]
    assert [record.getMessage() for record in records] == [
        entrypoint.KNOWLEDGE_UNAVAILABLE_WARNING
    ]
    assert records[0].args == ()


def test_existing_valid_current_calls_knowledge_index_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "generated"
    build = directory / "builds" / "build-20260806T000000000000Z"
    build.mkdir(parents=True)
    (directory / "current").symlink_to(build.relative_to(directory))
    embedder = object()
    sentinel = object()
    calls: list[tuple[object, object]] = []

    def load(*args: object) -> object:
        assert len(args) == 2
        calls.append((args[0], args[1]))
        return sentinel

    monkeypatch.setattr(entrypoint.KnowledgeIndex, "load", load)

    assert entrypoint._load_knowledge_retriever(directory, embedder) is sentinel
    assert calls == [(directory, embedder)]


@pytest.mark.parametrize("pointer_kind", ["regular_file", "broken", "invalid"])
def test_existing_malformed_current_propagates_index_failure(
    tmp_path: Path, pointer_kind: str
) -> None:
    directory = tmp_path / "generated"
    directory.mkdir()
    current = directory / "current"
    if pointer_kind == "regular_file":
        current.write_text("not a pointer", encoding="utf-8")
    elif pointer_kind == "broken":
        current.symlink_to(Path("builds") / "build-20260806T000000000000Z")
    else:
        current.symlink_to("invalid-target")

    with pytest.raises(BuildError):
        entrypoint._load_knowledge_retriever(directory, object())


@pytest.mark.asyncio
async def test_absent_current_starts_voice_session_and_defers_client_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = _install_lifecycle_fakes(
        monkeypatch,
        None,
        tmp_path / "generated",
        knowledge_available=False,
    )

    with caplog.at_level(logging.WARNING, logger="agent"):
        await entrypoint.my_agent(harness.context)  # type: ignore[arg-type]

    assert "index" not in harness.events
    state = harness.session.userdata
    assert state is not None
    assert isinstance(
        state.retriever,
        entrypoint.UnavailableKnowledgeRetriever,  # type: ignore[union-attr]
    )
    assert [
        record.getMessage() for record in caplog.records if record.name == "agent"
    ] == [entrypoint.KNOWLEDGE_UNAVAILABLE_WARNING]
    assert harness.client.aio.close_attempts == 0

    await harness.context.shutdown_callbacks[0]("normal shutdown")
    await harness.context.shutdown_callbacks[0]("duplicate shutdown")
    assert harness.client.aio.close_attempts == 1
