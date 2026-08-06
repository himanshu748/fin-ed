from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent as entrypoint
from fined.knowledge.ingest import BuildError
from fined.modes import LearningMode


class LifecycleAbort(BaseException):
    """Sentinel proving BaseException cleanup does not suppress the original failure."""


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

    def on(self, event_name: str):
        assert event_name == "metrics_collected"
        self.events.append("metrics_registration")
        if self.fail_at == "metrics_registration":
            raise LifecycleAbort("metrics_registration")

        def register(callback: object) -> object:
            return callback

        return register

    async def start(self, **kwargs: object) -> None:
        self.events.append("start")
        if self.fail_at == "start":
            raise LifecycleAbort("start")
        assert kwargs["room"] is not None

    async def say(self, greeting: str) -> None:
        self.events.append("say")
        if self.fail_at == "say":
            raise LifecycleAbort("say")
        assert "Financial Services" in greeting


class FakeContext:
    def __init__(self, events: list[str], fail_at: str | None) -> None:
        self.events = events
        self.fail_at = fail_at
        self.room = SimpleNamespace(name="test-room")
        self.proc = SimpleNamespace(userdata={"vad": object()})
        self.log_context_fields: dict[str, str] = {}
        self.shutdown_callbacks: list[Any] = []

    async def connect(self) -> None:
        self.events.append("connect")

    async def wait_for_participant(self) -> SimpleNamespace:
        self.events.append("participant")
        return SimpleNamespace(metadata='{"learning_mode":"stocks"}')

    def add_shutdown_callback(self, callback: Any) -> None:
        self.events.append("shutdown_registration")
        self.shutdown_callbacks.append(callback)
        if self.fail_at == "shutdown_registration":
            raise LifecycleAbort("shutdown_registration")


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
    monkeypatch.setattr(
        entrypoint, "MultilingualModel", stage("turn_detection", object())
    )
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
    for callback in harness.context.shutdown_callbacks:
        await callback("later shutdown")
    assert harness.client.aio.close_attempts == 1


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

    with pytest.raises(LifecycleAbort, match=fail_at):
        await callback("duplicate shutdown")
    assert harness.client.aio.close_attempts == 1


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
        "shutdown_registration",
        "start",
        "say",
    ]
    assert harness.client.aio.close_attempts == 0
    assert len(harness.context.shutdown_callbacks) == 1
    state = harness.session.userdata
    assert state is not None
    assert state.profile.learning_mode is LearningMode.STOCKS  # type: ignore[union-attr]
    assert harness.llm_kwargs == {
        "model": "gemini-3.6-flash",
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
    assert harness.session.kwargs["llm"] is harness.llm
    assert "conn_options" not in harness.session.kwargs

    callback = harness.context.shutdown_callbacks[0]
    await callback("normal shutdown")
    await callback("duplicate shutdown")

    assert harness.client.aio.close_attempts == 1


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
