from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from livekit.agents import DEFAULT_API_CONNECT_OPTIONS

from fined.provider_safety import ProviderErrorSanitizingLLM, sanitize_provider_llm

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_MAX_OUTPUT_TOKENS = 320
LIVEKIT_MAX_RETRY = DEFAULT_API_CONNECT_OPTIONS.max_retry
SUPPORTED_GEMINI_MODELS = frozenset(
    {
        DEFAULT_GEMINI_MODEL,
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
    }
)
SAFE_CONFIGURATION_ERROR = "Invalid GEMINI_MODEL configuration"

_THINKING_CONFIG_BY_MODEL: dict[str, dict[str, str | int]] = {
    "gemini-3.6-flash": {"thinking_level": "minimal"},
    "gemini-3.5-flash-lite": {"thinking_level": "minimal"},
    # Gemini 2.5 tool calls need a thought signature on the following turn.
    # A zero budget omits that signature and makes the tool response fail with 400.
    "gemini-2.5-flash": {"thinking_budget": 128},
}


class GeminiModelConfigurationError(ValueError):
    """Raised without echoing an invalid environment value."""


@dataclass(frozen=True)
class GeminiChatModelConfig:
    model: str
    thinking_config: dict[str, str | int]
    max_output_tokens: int = GEMINI_MAX_OUTPUT_TOKENS

    def constructor_kwargs(self) -> dict[str, object]:
        return {
            "model": self.model,
            "thinking_config": dict(self.thinking_config),
            "max_output_tokens": self.max_output_tokens,
        }


def resolve_gemini_chat_model(
    environment: Mapping[str, str] | None = None,
) -> GeminiChatModelConfig:
    """Resolve one exact supported model without trimming or fallback."""
    source = os.environ if environment is None else environment
    model = source.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if not isinstance(model, str) or model not in SUPPORTED_GEMINI_MODELS:
        raise GeminiModelConfigurationError(SAFE_CONFIGURATION_ERROR)
    return GeminiChatModelConfig(
        model=model,
        thinking_config=dict(_THINKING_CONFIG_BY_MODEL[model]),
    )


_T = TypeVar("_T")


def create_gemini_llm(
    constructor: Callable[..., _T],
    *,
    environment: Mapping[str, str] | None = None,
) -> _T | ProviderErrorSanitizingLLM:
    """Construct the configured LiveKit Gemini adapter exactly once."""
    config = resolve_gemini_chat_model(environment)
    thinking = (
        "minimal"
        if config.thinking_config.get("thinking_level") == "minimal"
        else "bounded"
    )
    logger.info(
        "Gemini chat configured: model=%s max_output_tokens=%d "
        "thinking=%s livekit_max_retry=%d",
        config.model,
        config.max_output_tokens,
        thinking,
        LIVEKIT_MAX_RETRY,
    )
    return sanitize_provider_llm(constructor(**config.constructor_kwargs()))
