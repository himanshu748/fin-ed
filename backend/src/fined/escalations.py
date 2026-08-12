"""Consent-gated, privacy-preserving requests for limited human help."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

_OTP_OR_PIN_VALUE = re.compile(
    r"\b(?:one[ -]?time(?:[ -]?(?:password|passcode|code))?|"
    r"otp(?:[ -]?(?:code|password|passcode))?|"
    r"m?[ -]?pin(?:[ -]?(?:code|number))?)\b"
    r"\s*(?:(?:is|:|=|-)\s*)?\d(?:[\d\s,.-]*\d)?",
    re.IGNORECASE,
)
_PASSWORD_VALUE = re.compile(
    r"\b(?:password|passcode|pwd)\b"
    r"(?:\s*(?:is|:|=|-)\s*|\s+)"
    r"(?:\"[^\"]*\"|'[^']*'|[^,;.\n]+)",
    re.IGNORECASE,
)
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_LONG_DIGIT_RUN = re.compile(r"(?<!\d)\d(?:[\s,.-]*\d){7,}(?!\d)")
_ANONYMOUS_CALLER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_REFERENCE_TOKEN = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)

ESCALATION_REASONS = frozenset({"suspected_fraud", "decision_review"})
URGENCY_LEVELS = frozenset({"low", "medium", "high", "emergency"})
CALLER_LANGUAGES = frozenset({"english", "hindi", "bilingual"})
FOLLOW_UP_METHODS = frozenset({"in_app"})
MAX_SUMMARY_BYTES = 480
MAX_CHECKS = 4
MAX_CHECK_BYTES = 240
MAX_TOTAL_CHECK_BYTES = 720
_ALLOWED_URGENCIES = {
    "suspected_fraud": frozenset({"high", "emergency"}),
    "decision_review": frozenset({"low", "medium", "high"}),
}
_URGENCY_RANK = {"low": 0, "medium": 1, "high": 2, "emergency": 3}


class EscalationConsentRequiredError(ValueError):
    """Raised when a caller has not explicitly approved this escalation."""


class EscalationValidationError(ValueError):
    """Raised when an escalation request is outside the narrow safe schema."""


@dataclass(frozen=True)
class EscalationRequestInput:
    """Private, minimal input for one consented request."""

    anonymous_caller_id: str
    reason: str
    urgency: str
    caller_language: str
    summary: str
    checks: Sequence[str]
    follow_up: str = "in_app"


@dataclass(frozen=True)
class EscalationRequest:
    """Dashboard-safe request data that intentionally omits the caller ID."""

    reference_id: str
    reason: str
    urgency: str
    caller_language: str
    summary: str
    checks: tuple[str, ...]
    follow_up: str
    status: str
    created_at: datetime


class EscalationStore(Protocol):
    def create(
        self,
        request: EscalationRequestInput,
        *,
        consent_confirmed: bool,
    ) -> EscalationRequest: ...

    def list_open(self) -> list[EscalationRequest]: ...


class SQLiteEscalationStore:
    """SQLite-backed store for explicitly consented, limited escalations."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_hex(12))
        self._initialize()

    def create(
        self,
        request: EscalationRequestInput,
        *,
        consent_confirmed: bool,
    ) -> EscalationRequest:
        if consent_confirmed is not True:
            raise EscalationConsentRequiredError(
                "Explicit consent is required before creating an escalation."
            )
        normalized = _validate_request(request)
        now = self._clock()
        if now.tzinfo is None:
            raise EscalationValidationError(
                "Escalation timestamps must include a timezone."
            )
        summary = _redact_sensitive_text(normalized.summary)
        checks = tuple(_redact_sensitive_text(check) for check in normalized.checks)
        caller_fingerprint = _caller_fingerprint(normalized.anonymous_caller_id)
        issue_fingerprint = _issue_fingerprint(
            reason=normalized.reason,
            caller_language=normalized.caller_language,
            summary=summary,
            checks=checks,
            follow_up=normalized.follow_up,
        )
        with self._connect() as connection:
            existing = self._find_open(
                connection, caller_fingerprint, issue_fingerprint
            )
            if existing is not None:
                return self._raise_urgency_if_needed(
                    connection, existing, normalized.urgency
                )
            for _ in range(3):
                reference_id = _reference_id(self._token_factory())
                try:
                    connection.execute(
                        """
                        INSERT INTO escalation_requests (
                            reference_id, caller_fingerprint, issue_fingerprint,
                            reason, urgency, caller_language, summary, checks_json,
                            follow_up, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                        """,
                        (
                            reference_id,
                            caller_fingerprint,
                            issue_fingerprint,
                            normalized.reason,
                            normalized.urgency,
                            normalized.caller_language,
                            summary,
                            json.dumps(
                                checks,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            normalized.follow_up,
                            now.isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    existing = self._find_open(
                        connection, caller_fingerprint, issue_fingerprint
                    )
                    if existing is not None:
                        return self._raise_urgency_if_needed(
                            connection, existing, normalized.urgency
                        )
                    continue
                return EscalationRequest(
                    reference_id=reference_id,
                    reason=normalized.reason,
                    urgency=normalized.urgency,
                    caller_language=normalized.caller_language,
                    summary=summary,
                    checks=checks,
                    follow_up=normalized.follow_up,
                    status="open",
                    created_at=now,
                )
        raise EscalationValidationError("Could not create a safe reference ID.")

    def _find_open(
        self,
        connection: sqlite3.Connection,
        caller_fingerprint: str,
        issue_fingerprint: str,
    ) -> EscalationRequest | None:
        row = connection.execute(
            """
            SELECT reference_id, reason, urgency, caller_language, summary,
                   checks_json, follow_up, status, created_at
            FROM escalation_requests
            WHERE caller_fingerprint = ?
              AND issue_fingerprint = ?
              AND status = 'open'
            """,
            (caller_fingerprint, issue_fingerprint),
        ).fetchone()
        return None if row is None else _request_from_row(row)

    def _raise_urgency_if_needed(
        self,
        connection: sqlite3.Connection,
        existing: EscalationRequest,
        requested_urgency: str,
    ) -> EscalationRequest:
        if _URGENCY_RANK[requested_urgency] <= _URGENCY_RANK[existing.urgency]:
            return existing
        connection.execute(
            "UPDATE escalation_requests SET urgency = ? WHERE reference_id = ?",
            (requested_urgency, existing.reference_id),
        )
        return replace(existing, urgency=requested_urgency)

    def list_open(self) -> list[EscalationRequest]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT reference_id, reason, urgency, caller_language, summary,
                       checks_json, follow_up, status, created_at
                FROM escalation_requests
                WHERE status = 'open'
                ORDER BY created_at, reference_id
                """
            ).fetchall()
        return [_request_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS escalation_requests (
                    reference_id TEXT PRIMARY KEY,
                    caller_fingerprint TEXT NOT NULL,
                    issue_fingerprint TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    caller_language TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    checks_json TEXT NOT NULL,
                    follow_up TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS escalation_requests_open_issue
                ON escalation_requests (caller_fingerprint, issue_fingerprint, status)
                """
            )


def _caller_fingerprint(anonymous_caller_id: str) -> str:
    return hashlib.sha256(
        f"fined-escalation-caller-v1:{anonymous_caller_id}".encode()
    ).hexdigest()


def _reference_id(token: object) -> str:
    if not isinstance(token, str) or _REFERENCE_TOKEN.fullmatch(token) is None:
        raise EscalationValidationError("Could not create a safe reference ID.")
    token = token.upper()
    return "HELP-" + "-".join(token[index : index + 4] for index in range(0, 24, 4))


def _issue_fingerprint(
    *,
    reason: str,
    caller_language: str,
    summary: str,
    checks: tuple[str, ...],
    follow_up: str,
) -> str:
    payload = json.dumps(
        {
            "caller_language": caller_language,
            "checks": checks,
            "follow_up": follow_up,
            "reason": reason,
            "summary": summary,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(f"fined-escalation-issue-v1:{payload}".encode()).hexdigest()


def _validate_request(request: object) -> EscalationRequestInput:
    if not isinstance(request, EscalationRequestInput):
        raise EscalationValidationError("An escalation request is required.")
    caller_id = _validate_anonymous_caller_id(request.anonymous_caller_id)
    reason = _validate_choice(request.reason, "reason", ESCALATION_REASONS)
    urgency = _validate_choice(request.urgency, "urgency", URGENCY_LEVELS)
    if urgency not in _ALLOWED_URGENCIES[reason]:
        raise EscalationValidationError(
            f"urgency {urgency!r} is not allowed for {reason!r}."
        )
    language = _validate_choice(
        request.caller_language, "caller_language", CALLER_LANGUAGES
    )
    follow_up = _validate_choice(request.follow_up, "follow_up", FOLLOW_UP_METHODS)
    summary = _validate_text(
        request.summary, "summary", maximum_bytes=MAX_SUMMARY_BYTES
    )
    if isinstance(request.checks, (str, bytes)) or not isinstance(
        request.checks, Sequence
    ):
        raise EscalationValidationError("checks must be a sequence of short text.")
    if not 1 <= len(request.checks) <= MAX_CHECKS:
        raise EscalationValidationError(
            f"Store between one and {MAX_CHECKS} concise checks."
        )
    checks = tuple(
        _validate_text(check, "checks", maximum_bytes=MAX_CHECK_BYTES)
        for check in request.checks
    )
    if sum(len(check.encode("utf-8")) for check in checks) > MAX_TOTAL_CHECK_BYTES:
        raise EscalationValidationError("checks are too long.")
    return EscalationRequestInput(
        anonymous_caller_id=caller_id,
        reason=reason,
        urgency=urgency,
        caller_language=language,
        summary=summary,
        checks=checks,
        follow_up=follow_up,
    )


def _validate_anonymous_caller_id(value: object) -> str:
    if not isinstance(value, str) or _ANONYMOUS_CALLER_ID.fullmatch(value) is None:
        raise EscalationValidationError("anonymous_caller_id is invalid.")
    return value


def _validate_choice(value: object, field: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise EscalationValidationError(f"{field} is invalid.")
    return value


def _validate_text(value: object, field: str, *, maximum_bytes: int) -> str:
    if not isinstance(value, str) or value.strip() != value or not value:
        raise EscalationValidationError(f"{field} must be non-empty trimmed text.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise EscalationValidationError(f"{field} must be valid UTF-8 text.") from None
    if len(encoded) > maximum_bytes or any(ord(character) < 32 for character in value):
        raise EscalationValidationError(
            f"{field} is too long or contains control text."
        )
    return value


def _redact_sensitive_text(value: str) -> str:
    value = _OTP_OR_PIN_VALUE.sub("[REDACTED]", value)
    value = _PASSWORD_VALUE.sub("[REDACTED]", value)
    value = _PAN.sub("[REDACTED]", value)
    return _LONG_DIGIT_RUN.sub("[REDACTED]", value)


def _request_from_row(row: tuple[object, ...]) -> EscalationRequest:
    checks = json.loads(row[5])
    return EscalationRequest(
        reference_id=row[0],
        reason=row[1],
        urgency=row[2],
        caller_language=row[3],
        summary=row[4],
        checks=tuple(checks),
        follow_up=row[6],
        status=row[7],
        created_at=datetime.fromisoformat(row[8]),
    )
