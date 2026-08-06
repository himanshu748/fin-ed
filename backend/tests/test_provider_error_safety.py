from __future__ import annotations

import importlib
import logging
import traceback
from collections.abc import Callable
from typing import Any

import pytest
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIError,
    APIStatusError,
    llm,
)

from fined.chat_model import create_gemini_llm

PROVIDER_MESSAGE_SENTINEL = "SECRET_PROVIDER_MESSAGE"
PROVIDER_BODY_SENTINEL = "SECRET_PROVIDER_BODY"
PROVIDER_REQUEST_ID_SENTINEL = "SECRET_PROVIDER_REQUEST_ID"
PROVIDER_CAUSE_SENTINEL = "SECRET_PROVIDER_CAUSE"
SYNCHRONOUS_UNEXPECTED_SENTINEL = "SECRET_SYNC_PROVIDER_EXCEPTION"


def _retryable_status_error_with_raw_cause() -> APIStatusError:
    try:
        try:
            raise RuntimeError(PROVIDER_CAUSE_SENTINEL)
        except RuntimeError as provider_cause:
            raise APIStatusError(
                PROVIDER_MESSAGE_SENTINEL,
                status_code=429,
                request_id=PROVIDER_REQUEST_ID_SENTINEL,
                body=PROVIDER_BODY_SENTINEL,
                retryable=True,
            ) from provider_cause
    except APIStatusError as error:
        return error


class _FailingLLM(llm.LLM):
    def __init__(self, error_factory: Callable[[], APIError]) -> None:
        super().__init__()
        self.error_factory = error_factory
        self.attempts = 0

    @property
    def model(self) -> str:
        return "gemini-3.6-flash"

    @property
    def provider(self) -> str:
        return "Google"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions,
        **_: Any,
    ) -> llm.LLMStream:
        return _FailingStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )


class _FailingStream(llm.LLMStream):
    async def _run(self) -> None:
        failing_llm = self._llm
        assert isinstance(failing_llm, _FailingLLM)
        failing_llm.attempts += 1
        raise failing_llm.error_factory()


class _SynchronousFailingLLM(llm.LLM):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error
        self.chat_calls = 0

    @property
    def model(self) -> str:
        return "gemini-3.6-flash"

    @property
    def provider(self) -> str:
        return "Google"

    def chat(self, **_: Any) -> llm.LLMStream:
        self.chat_calls += 1
        raise self.error


def _configured_failing_llm(
    error_factory: Callable[[], APIError],
) -> tuple[llm.LLM, _FailingLLM]:
    provider_llm = _FailingLLM(error_factory)
    configured = create_gemini_llm(
        lambda **_: provider_llm,
        environment={"GEMINI_MODEL": "gemini-3.6-flash"},
    )
    assert isinstance(configured, llm.LLM)
    return configured, provider_llm


def _capture_livekit_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    captured: list[str] = []
    livekit_llm_module = importlib.import_module("livekit.agents.llm.llm")

    def capture_exception(_span: object, error: Exception) -> None:
        captured.extend(
            [
                str(error),
                repr(error),
                "".join(traceback.format_exception(error)),
                traceback.format_exc(),
            ]
        )

    monkeypatch.setattr(
        livekit_llm_module.telemetry_utils,
        "record_exception",
        capture_exception,
    )
    return captured


def _exposed_error_text(
    *,
    caplog: pytest.LogCaptureFixture,
    telemetry: list[str],
    emitted_errors: list[Exception],
    raised_error: BaseException,
) -> str:
    return "\n".join(
        [
            *(record.getMessage() for record in caplog.records),
            *telemetry,
            *(str(error) for error in emitted_errors),
            *(repr(error) for error in emitted_errors),
            "".join(traceback.format_exception(raised_error)),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_factory", "safe_context"),
    [
        pytest.param(
            _retryable_status_error_with_raw_cause,
            "status_code=429",
            id="provider-body",
        ),
        pytest.param(
            lambda: APIConnectionError(
                f"wrapped unexpected exception: {PROVIDER_MESSAGE_SENTINEL}",
                retryable=True,
            ),
            "LLM provider connection error",
            id="wrapped-unexpected-exception",
        ),
    ],
)
async def test_retryable_provider_details_are_sanitized_before_livekit_retry_logging(
    error_factory: Callable[[], APIError],
    safe_context: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, provider_llm = _configured_failing_llm(error_factory)
    telemetry = _capture_livekit_telemetry(monkeypatch)
    emitted_errors: list[Exception] = []
    recoverable: list[bool] = []

    def capture_error(event: llm.LLMError) -> None:
        emitted_errors.append(event.error)
        recoverable.append(event.recoverable)

    model.on("error", capture_error)
    options = APIConnectOptions(max_retry=3, retry_interval=0, timeout=10)

    with (
        caplog.at_level(logging.WARNING, logger="livekit.agents"),
        pytest.raises(APIConnectionError) as exc_info,
    ):
        await model.chat(
            chat_ctx=llm.ChatContext.empty(),
            conn_options=options,
        ).collect()

    exposed = _exposed_error_text(
        caplog=caplog,
        telemetry=telemetry,
        emitted_errors=emitted_errors,
        raised_error=exc_info.value,
    )
    assert provider_llm.attempts == 4
    assert recoverable == [True, True, True, False]
    assert len(telemetry) == 16
    assert (
        len([record for record in caplog.records if record.levelno >= logging.WARNING])
        == 3
    )
    assert safe_context in exposed
    assert "retryable=True" in exposed
    assert model.model == "gemini-3.6-flash"
    assert model.provider == "Google"
    assert all(error.__cause__ is None for error in emitted_errors)
    assert all(error.__context__ is None for error in emitted_errors)
    assert PROVIDER_MESSAGE_SENTINEL not in exposed
    assert PROVIDER_BODY_SENTINEL not in exposed
    assert PROVIDER_REQUEST_ID_SENTINEL not in exposed
    assert PROVIDER_CAUSE_SENTINEL not in exposed


def test_synchronous_provider_api_error_is_sanitized_at_chat_boundary() -> None:
    provider_llm = _SynchronousFailingLLM(
        APIStatusError(
            PROVIDER_MESSAGE_SENTINEL,
            status_code=429,
            request_id=PROVIDER_REQUEST_ID_SENTINEL,
            body=PROVIDER_BODY_SENTINEL,
            retryable=True,
        )
    )
    model = create_gemini_llm(
        lambda **_: provider_llm,
        environment={"GEMINI_MODEL": "gemini-3.6-flash"},
    )
    assert isinstance(model, llm.LLM)

    with pytest.raises(APIStatusError) as exc_info:
        model.chat(chat_ctx=llm.ChatContext.empty())

    error = exc_info.value
    exposed = "\n".join(
        [str(error), repr(error), "".join(traceback.format_exception(error))]
    )
    assert provider_llm.chat_calls == 1
    assert error.status_code == 429
    assert error.retryable is True
    assert error.body is None
    assert error.request_id is None
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "LLM provider status error" in exposed
    assert PROVIDER_MESSAGE_SENTINEL not in exposed
    assert PROVIDER_BODY_SENTINEL not in exposed
    assert PROVIDER_REQUEST_ID_SENTINEL not in exposed


def test_synchronous_unexpected_provider_exception_is_sanitized_once() -> None:
    provider_llm = _SynchronousFailingLLM(RuntimeError(SYNCHRONOUS_UNEXPECTED_SENTINEL))
    model = create_gemini_llm(
        lambda **_: provider_llm,
        environment={"GEMINI_MODEL": "gemini-3.6-flash"},
    )
    assert isinstance(model, llm.LLM)

    with pytest.raises(RuntimeError) as exc_info:
        model.chat(chat_ctx=llm.ChatContext.empty())

    error = exc_info.value
    exposed = "\n".join(
        [str(error), repr(error), "".join(traceback.format_exception(error))]
    )
    assert provider_llm.chat_calls == 1
    assert str(error) == "LLM provider raised an unexpected error"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert SYNCHRONOUS_UNEXPECTED_SENTINEL not in exposed


def test_raw_provider_error_event_is_rebuilt_before_forwarding() -> None:
    provider_llm = _FailingLLM(lambda: APIConnectionError(retryable=False))
    model = create_gemini_llm(
        lambda **_: provider_llm,
        environment={"GEMINI_MODEL": "gemini-3.6-flash"},
    )
    assert isinstance(model, llm.LLM)
    forwarded: list[llm.LLMError] = []
    model.on("error", forwarded.append)

    provider_llm.emit(
        "error",
        llm.LLMError(
            timestamp=1.0,
            label="livekit.plugins.google.LLM",
            error=APIStatusError(
                PROVIDER_MESSAGE_SENTINEL,
                status_code=429,
                request_id=PROVIDER_REQUEST_ID_SENTINEL,
                body=PROVIDER_BODY_SENTINEL,
                retryable=True,
            ),
            recoverable=True,
        ),
    )

    assert len(forwarded) == 1
    event = forwarded[0]
    assert event.timestamp == 1.0
    assert event.label == "livekit.plugins.google.LLM"
    assert event.recoverable is True
    assert isinstance(event.error, APIStatusError)
    assert event.error.status_code == 429
    assert event.error.retryable is True
    assert event.error.body is None
    assert event.error.request_id is None
    exposed = f"{event.error!s}\n{event.error!r}"
    assert PROVIDER_MESSAGE_SENTINEL not in exposed
    assert PROVIDER_BODY_SENTINEL not in exposed
    assert PROVIDER_REQUEST_ID_SENTINEL not in exposed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_factory", "safe_category"),
    [
        pytest.param(
            lambda: APIStatusError(
                PROVIDER_MESSAGE_SENTINEL,
                status_code=400,
                request_id=PROVIDER_REQUEST_ID_SENTINEL,
                body=PROVIDER_BODY_SENTINEL,
                retryable=False,
            ),
            "LLM provider status error",
            id="nonretryable-status",
        ),
        pytest.param(
            lambda: APIConnectionError(
                f"wrapped unexpected exception: {PROVIDER_MESSAGE_SENTINEL}",
                retryable=False,
            ),
            "LLM provider connection error",
            id="wrapped-unexpected-exception",
        ),
    ],
)
async def test_nonretryable_provider_details_are_sanitized_without_adding_a_retry(
    error_factory: Callable[[], APIError],
    safe_category: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, provider_llm = _configured_failing_llm(error_factory)
    telemetry = _capture_livekit_telemetry(monkeypatch)
    emitted_errors: list[Exception] = []
    model.on("error", lambda event: emitted_errors.append(event.error))
    options = APIConnectOptions(max_retry=3, retry_interval=0, timeout=10)

    with (
        caplog.at_level(logging.WARNING, logger="livekit.agents"),
        pytest.raises(APIError) as exc_info,
    ):
        await model.chat(
            chat_ctx=llm.ChatContext.empty(),
            conn_options=options,
        ).collect()

    exposed = _exposed_error_text(
        caplog=caplog,
        telemetry=telemetry,
        emitted_errors=emitted_errors,
        raised_error=exc_info.value,
    )
    assert provider_llm.attempts == 1
    assert len(emitted_errors) == 1
    assert len(telemetry) == 4
    assert not caplog.records
    assert safe_category in exposed
    assert model.model == "gemini-3.6-flash"
    assert model.provider == "Google"
    assert exc_info.value.__cause__ is None
    assert all(error.__cause__ is None for error in emitted_errors)
    if isinstance(exc_info.value, APIStatusError):
        assert exc_info.value.status_code == 400
        assert exc_info.value.retryable is False
        assert exc_info.value.body is None
        assert exc_info.value.request_id is None
    assert PROVIDER_MESSAGE_SENTINEL not in exposed
    assert PROVIDER_BODY_SENTINEL not in exposed
    assert PROVIDER_REQUEST_ID_SENTINEL not in exposed
