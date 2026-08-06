from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectionError,
    APIConnectOptions,
    APIError,
    APIStatusError,
    APITimeoutError,
    NotGivenOr,
    llm,
)

_SAFE_CONNECTION_ERROR = "LLM provider connection error"
_SAFE_PROVIDER_ERROR = "LLM provider request error"
_SAFE_STATUS_ERROR = "LLM provider status error"
_SAFE_TIMEOUT_ERROR = "LLM provider timeout"
_SAFE_UNEXPECTED_ERROR = "LLM provider raised an unexpected error"


def _sanitized_api_error(error: APIError) -> APIError:
    """Keep retry semantics and safe categories, but discard provider detail."""
    if isinstance(error, APIStatusError):
        return APIStatusError(
            _SAFE_STATUS_ERROR,
            status_code=error.status_code,
            retryable=error.retryable,
        )
    if isinstance(error, APITimeoutError):
        return APITimeoutError(
            _SAFE_TIMEOUT_ERROR,
            retryable=error.retryable,
        )
    if isinstance(error, APIConnectionError):
        return APIConnectionError(
            _SAFE_CONNECTION_ERROR,
            retryable=error.retryable,
        )
    return APIError(
        _SAFE_PROVIDER_ERROR,
        retryable=error.retryable,
    )


def _sanitized_provider_exception(error: Exception) -> Exception:
    if isinstance(error, APIError):
        return _sanitized_api_error(error)
    return RuntimeError(_SAFE_UNEXPECTED_ERROR)


def _sanitize_stream_errors(stream: llm.LLMStream) -> llm.LLMStream:
    """Sanitize before LiveKit's retry loop records or logs the exception.

    LiveKit 1.4 starts its retry task in ``LLMStream.__init__`` and does not expose
    a public exception-transform hook. ``LLM.chat`` is synchronous, so replacing
    the protected provider operation immediately after ``chat`` returns happens
    before that task can run. Keep this compatibility seam isolated here.
    """
    provider_run = stream._run

    async def sanitized_run() -> None:
        safe_error: Exception | None = None
        try:
            await provider_run()
        except Exception as error:
            safe_error = _sanitized_provider_exception(error)

        # Raise outside the except block so the sanitized error has no raw
        # provider exception in __context__ or __cause__ for telemetry to walk.
        if safe_error is not None:
            raise safe_error

    stream._run = sanitized_run  # type: ignore[method-assign]
    return stream


class ProviderErrorSanitizingLLM(llm.LLM):
    """Public LLM adapter that redacts provider failures before LiveKit sees them."""

    def __init__(self, provider_llm: llm.LLM) -> None:
        super().__init__()
        self._provider_llm = provider_llm
        self._provider_llm.on("metrics_collected", self._forward_metrics)
        self._provider_llm.on("error", self._forward_error)

    @property
    def model(self) -> str:
        return self._provider_llm.model

    @property
    def label(self) -> str:
        return self._provider_llm.label

    @property
    def provider(self) -> str:
        return self._provider_llm.provider

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        stream: llm.LLMStream | None = None
        safe_error: Exception | None = None
        try:
            stream = self._provider_llm.chat(
                chat_ctx=chat_ctx,
                tools=tools,
                conn_options=conn_options,
                parallel_tool_calls=parallel_tool_calls,
                tool_choice=tool_choice,
                extra_kwargs=extra_kwargs,
            )
        except Exception as error:
            safe_error = _sanitized_provider_exception(error)

        if safe_error is not None:
            raise safe_error
        assert stream is not None
        return _sanitize_stream_errors(stream)

    def prewarm(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if loop is None:
            self._provider_llm.prewarm()
        else:
            self._provider_llm.prewarm(loop=loop)

    async def aclose(self) -> None:
        try:
            await self._provider_llm.aclose()
        finally:
            self._provider_llm.off("metrics_collected", self._forward_metrics)
            self._provider_llm.off("error", self._forward_error)

    def _forward_metrics(self, *args: Any, **kwargs: Any) -> None:
        self.emit("metrics_collected", *args, **kwargs)

    def _forward_error(self, event: llm.LLMError) -> None:
        self.emit(
            "error",
            event.model_copy(
                update={"error": _sanitized_provider_exception(event.error)}
            ),
        )


_T = TypeVar("_T")


def sanitize_provider_llm(model: _T) -> _T | ProviderErrorSanitizingLLM:
    """Wrap LiveKit LLM instances; leave constructor test doubles untouched."""
    if not isinstance(model, llm.LLM):
        return model
    if isinstance(model, ProviderErrorSanitizingLLM):
        return model
    return ProviderErrorSanitizingLLM(model)
