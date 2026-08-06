from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

from fined.modes import LearningMode

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_ALLOWED_KEYS = {
    "source_id",
    "publisher",
    "authority",
    "url",
    "topics",
    "broker",
    "verified_on",
    "status",
    "effective_from",
    "effective_to",
    "expected_terms",
}
_REQUIRED_KEYS = {
    "source_id",
    "publisher",
    "authority",
    "url",
    "topics",
    "broker",
    "verified_on",
    "status",
    "expected_terms",
}


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    publisher: str
    authority: str
    url: str
    topics: tuple[LearningMode, ...]
    broker: str | None
    verified_on: date
    expected_terms: tuple[str, ...]
    required: bool = True
    effective_from: date | None = None
    effective_to: date | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SourceSpec:
        if not isinstance(value, dict):
            raise ValueError("source <unknown>: entry must be an object")
        source_id = value.get("source_id", "<unknown>")
        if not isinstance(source_id, str):
            source_id = "<unknown>"

        unknown = sorted(set(value) - _ALLOWED_KEYS)
        if unknown:
            raise ValueError(
                f"source {source_id}: unknown manifest keys: {', '.join(unknown)}"
            )
        missing = sorted(_REQUIRED_KEYS - set(value))
        if missing:
            raise ValueError(
                f"source {source_id}: missing required keys: {', '.join(missing)}"
            )
        if not _SOURCE_ID.fullmatch(source_id):
            raise ValueError(f"source {source_id}: source_id must use snake_case")

        publisher = _required_text(value, "publisher", source_id)
        authority = _required_text(value, "authority", source_id)
        url = _required_text(value, "url", source_id)
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError(f"source {source_id}: url must be an absolute HTTPS URL")

        raw_topics = value["topics"]
        if not isinstance(raw_topics, list) or not raw_topics:
            raise ValueError(f"source {source_id}: topics must be a non-empty list")
        try:
            topics = tuple(LearningMode(topic) for topic in raw_topics)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"source {source_id}: topics contains an invalid mode"
            ) from exc
        if len(set(topics)) != len(topics):
            raise ValueError(f"source {source_id}: topics must not contain duplicates")

        raw_expected_terms = value["expected_terms"]
        if not isinstance(raw_expected_terms, list) or not raw_expected_terms:
            raise ValueError(
                f"source {source_id}: expected_terms must be a non-empty list"
            )
        if any(
            not isinstance(term, str) or not term.strip() for term in raw_expected_terms
        ):
            raise ValueError(
                f"source {source_id}: expected_terms must contain non-empty text"
            )
        expected_terms = tuple(term.strip() for term in raw_expected_terms)
        if len({term.casefold() for term in expected_terms}) != len(expected_terms):
            raise ValueError(
                f"source {source_id}: expected_terms must not contain duplicates"
            )

        broker = value["broker"]
        if broker is not None and (not isinstance(broker, str) or not broker.strip()):
            raise ValueError(f"source {source_id}: broker must be text or null")

        status = value["status"]
        if status not in {"required", "optional"}:
            raise ValueError(
                f"source {source_id}: status must be 'required' or 'optional'"
            )
        verified_on = _parse_date(value["verified_on"], "verified_on", source_id)
        effective_from = _parse_optional_date(value, "effective_from", source_id)
        effective_to = _parse_optional_date(value, "effective_to", source_id)
        if effective_from and effective_to and effective_from > effective_to:
            raise ValueError(
                f"source {source_id}: effective_from must not follow effective_to"
            )

        return cls(
            source_id=source_id,
            publisher=publisher,
            authority=authority,
            url=url,
            topics=topics,
            broker=broker.strip() if isinstance(broker, str) else None,
            verified_on=verified_on,
            expected_terms=expected_terms,
            required=status == "required",
            effective_from=effective_from,
            effective_to=effective_to,
        )

    @classmethod
    def example(cls) -> SourceSpec:
        return cls(
            source_id="angel_dp",
            publisher="Angel One",
            authority="broker_support",
            url="https://www.angelone.in/support/charges-and-cashbacks/dp-charges",
            topics=(LearningMode.STOCKS,),
            broker="Angel One",
            verified_on=date(2026, 8, 6),
            expected_terms=("DP charge",),
        )


@dataclass(frozen=True)
class ExtractedBlock:
    heading_path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    source: SourceSpec
    title: str
    text: str
    blocks: tuple[ExtractedBlock, ...]


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source_id: str
    publisher: str
    authority: str
    title: str
    heading_path: tuple[str, ...]
    text: str
    url: str
    topics: tuple[LearningMode, ...]
    broker: str | None
    verified_on: date
    effective_from: date | None
    effective_to: date | None


def _required_text(value: dict[str, Any], key: str, source_id: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"source {source_id}: {key} must be non-empty text")
    return item.strip()


def _parse_date(value: object, key: str, source_id: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"source {source_id}: {key} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"source {source_id}: invalid {key} date {value!r}") from exc


def _parse_optional_date(
    value: dict[str, Any], key: str, source_id: str
) -> date | None:
    item = value.get(key)
    if item is None:
        return None
    return _parse_date(item, key, source_id)
