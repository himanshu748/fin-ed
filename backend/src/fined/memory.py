"""Consent-gated, persistent caller memory for safe learning context."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

SAFE_FACT_KEYS = frozenset(
    {
        "experience_level",
        "learning_goal",
        "preferred_explanation_style",
        "topic_covered",
    }
)
LANGUAGE_PREFERENCES = frozenset({"english", "hindi", "bilingual"})
_CALLER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){8,}\d?(?!\d)")


class MemoryConsentRequiredError(ValueError):
    """Raised when a write or deletion lacks explicit caller consent."""


class MemoryValidationError(ValueError):
    """Raised when caller memory is unsafe or outside the small schema."""


@dataclass(frozen=True)
class CallerMemoryInput:
    caller_id: str
    name: str
    language_preference: str
    facts: Mapping[str, str]


@dataclass(frozen=True)
class CallerMemory:
    caller_id: str
    name: str
    language_preference: str
    facts: dict[str, str]
    last_interaction: datetime


class CallerMemoryStore(Protocol):
    def lookup(self, caller_id: str) -> CallerMemory | None: ...

    def save(
        self,
        memory: CallerMemoryInput,
        *,
        consent_confirmed: bool,
    ) -> CallerMemory: ...

    def forget(self, caller_id: str, *, consent_confirmed: bool) -> bool: ...


class SQLiteCallerMemoryStore:
    """Small SQLite store that keeps only allowlisted learning facts."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._initialize()

    def lookup(self, caller_id: str) -> CallerMemory | None:
        normalized_id = _validate_caller_id(caller_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT caller_id, name, language_preference, facts_json,
                       last_interaction
                FROM caller_memory
                WHERE caller_id = ?
                """,
                (normalized_id,),
            ).fetchone()
        if row is None:
            return None
        facts = json.loads(row[3])
        if not isinstance(facts, dict):
            raise MemoryValidationError("Stored caller memory is invalid.")
        timestamp = datetime.fromisoformat(row[4])
        if timestamp.tzinfo is None:
            raise MemoryValidationError("Stored caller memory is invalid.")
        return CallerMemory(
            caller_id=row[0],
            name=row[1],
            language_preference=row[2],
            facts=facts,
            last_interaction=timestamp,
        )

    def save(
        self,
        memory: CallerMemoryInput,
        *,
        consent_confirmed: bool,
    ) -> CallerMemory:
        if consent_confirmed is not True:
            raise MemoryConsentRequiredError(
                "Explicit consent is required before saving."
            )
        normalized = _validate_memory(memory)
        now = self._clock()
        if now.tzinfo is None:
            raise MemoryValidationError("Memory timestamps must include a timezone.")
        facts_json = json.dumps(
            normalized.facts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO caller_memory (
                    caller_id, name, language_preference, facts_json,
                    last_interaction
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(caller_id) DO UPDATE SET
                    name = excluded.name,
                    language_preference = excluded.language_preference,
                    facts_json = excluded.facts_json,
                    last_interaction = excluded.last_interaction
                """,
                (
                    normalized.caller_id,
                    normalized.name,
                    normalized.language_preference,
                    facts_json,
                    now.isoformat(),
                ),
            )
        return CallerMemory(
            caller_id=normalized.caller_id,
            name=normalized.name,
            language_preference=normalized.language_preference,
            facts=dict(normalized.facts),
            last_interaction=now,
        )

    def forget(self, caller_id: str, *, consent_confirmed: bool) -> bool:
        if consent_confirmed is not True:
            raise MemoryConsentRequiredError(
                "Explicit consent is required before deletion."
            )
        normalized_id = _validate_caller_id(caller_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM caller_memory WHERE caller_id = ?", (normalized_id,)
            )
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS caller_memory (
                    caller_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language_preference TEXT NOT NULL,
                    facts_json TEXT NOT NULL,
                    last_interaction TEXT NOT NULL
                )
                """
            )


def _validate_memory(memory: CallerMemoryInput) -> CallerMemoryInput:
    caller_id = _validate_caller_id(memory.caller_id)
    name = _validate_text(memory.name, "name", maximum_bytes=80)
    language = memory.language_preference
    if language not in LANGUAGE_PREFERENCES:
        raise MemoryValidationError(
            "language_preference must be english, hindi, or bilingual."
        )
    if not isinstance(memory.facts, Mapping):
        raise MemoryValidationError("facts must be a mapping.")
    if not 2 <= len(memory.facts) <= 4:
        raise MemoryValidationError("Store between two and four safe learning facts.")
    if not set(memory.facts).issubset(SAFE_FACT_KEYS):
        raise MemoryValidationError("Only safe learning facts may be stored.")
    facts = {
        key: _validate_text(value, key, maximum_bytes=200)
        for key, value in memory.facts.items()
    }
    return CallerMemoryInput(
        caller_id=caller_id,
        name=name,
        language_preference=language,
        facts=facts,
    )


def _validate_caller_id(value: object) -> str:
    if not isinstance(value, str) or _CALLER_ID.fullmatch(value) is None:
        raise MemoryValidationError("caller_id is invalid.")
    return value


def _validate_text(value: object, field: str, *, maximum_bytes: int) -> str:
    if not isinstance(value, str) or value.strip() != value or not value:
        raise MemoryValidationError(f"{field} must be non-empty trimmed text.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise MemoryValidationError(f"{field} must be valid UTF-8 text.") from None
    if len(encoded) > maximum_bytes or any(ord(character) < 32 for character in value):
        raise MemoryValidationError(f"{field} is too long or contains control text.")
    if _PAN.search(value) or _LONG_NUMBER.search(value):
        raise MemoryValidationError(
            f"{field} must not contain an account, PAN, Aadhaar, or financial ID."
        )
    return value
