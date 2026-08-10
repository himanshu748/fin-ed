from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from types import ModuleType
from typing import Any

import pytest
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, AgentSession

from fined.knowledge.embeddings import GeminiEmbedder


def chat_model_module() -> ModuleType:
    try:
        return importlib.import_module("fined.chat_model")
    except ModuleNotFoundError:
        pytest.fail("fined.chat_model is required", pytrace=False)


def test_default_model_is_available_flash_lite_with_voice_limits() -> None:
    chat_model = chat_model_module()

    config = chat_model.resolve_gemini_chat_model({})

    assert config.model == "gemini-3.5-flash-lite"
    assert config.thinking_config == {"thinking_level": "minimal"}
    assert config.max_output_tokens == 320


@pytest.mark.parametrize(
    ("model", "thinking_config"),
    [
        ("gemini-3.6-flash", {"thinking_level": "minimal"}),
        ("gemini-3.5-flash-lite", {"thinking_level": "minimal"}),
        ("gemini-2.5-flash", {"thinking_budget": 128}),
    ],
)
def test_supported_explicit_model_builds_exact_livekit_kwargs(
    model: str, thinking_config: dict[str, str | int]
) -> None:
    chat_model = chat_model_module()
    calls: list[dict[str, object]] = []
    created = object()

    def constructor(**kwargs: object) -> object:
        calls.append(kwargs)
        return created

    result = chat_model.create_gemini_llm(
        constructor,
        environment={"GEMINI_MODEL": model},
    )

    assert result is created
    assert calls == [
        {
            "model": model,
            "thinking_config": thinking_config,
            "max_output_tokens": 320,
        }
    ]
    assert {"temperature", "top_p", "top_k"}.isdisjoint(calls[0])


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        "\tgemini-3.6-flash",
        "gemini-3.6-flash ",
        "gemini-3.5-flash",
        "gemini-pro",
    ],
)
def test_invalid_model_configuration_fails_with_one_safe_error(value: str) -> None:
    chat_model = chat_model_module()

    with pytest.raises(
        chat_model.GeminiModelConfigurationError,
        match=r"^Invalid GEMINI_MODEL configuration$",
    ):
        chat_model.resolve_gemini_chat_model({"GEMINI_MODEL": value})


def test_provider_failure_is_not_retried_or_switched_to_another_model() -> None:
    chat_model = chat_model_module()
    calls: list[dict[str, object]] = []

    class ProviderError(RuntimeError):
        pass

    def failing_constructor(**kwargs: object) -> object:
        calls.append(kwargs)
        raise ProviderError("provider detail")

    with pytest.raises(ProviderError, match="provider detail"):
        chat_model.create_gemini_llm(
            failing_constructor,
            environment={"GEMINI_MODEL": "gemini-3.5-flash-lite"},
        )

    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-3.5-flash-lite"


def test_configuration_log_contains_only_non_secret_bounded_settings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    chat_model = chat_model_module()
    environment: Mapping[str, str] = {
        "GEMINI_MODEL": "gemini-3.6-flash",
        "GOOGLE_API_KEY": "must-not-appear",
    }

    with caplog.at_level(logging.INFO, logger="fined.chat_model"):
        chat_model.create_gemini_llm(lambda **kwargs: kwargs, environment=environment)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Gemini chat configured: model=gemini-3.6-flash "
        "max_output_tokens=320 thinking=minimal livekit_max_retry=3"
    ]
    assert "must-not-appear" not in "".join(messages)


@pytest.mark.asyncio
async def test_livekit_agent_session_default_retry_policy_is_bounded() -> None:
    session = AgentSession()
    options = session.conn_options.llm_conn_options

    assert options is DEFAULT_API_CONNECT_OPTIONS
    assert options.max_retry == 3
    assert options.retry_interval == 2.0
    assert options.timeout == 10.0


def test_embedding_model_and_artifact_dimension_are_unchanged() -> None:
    identity: dict[str, Any] = {
        "embedding_model": GeminiEmbedder.model,
        "embedding_dimension": GeminiEmbedder.dimensions,
    }

    assert identity == {
        "embedding_model": "gemini-embedding-001",
        "embedding_dimension": 768,
    }
