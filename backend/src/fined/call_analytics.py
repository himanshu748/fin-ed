"""Privacy-safe call outcomes and a public aggregate dashboard snapshot."""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CALL_SUCCESS_DEFINITION = (
    "The learner completed a verified action: received grounded market evidence, "
    "received trusted market or historical data, completed a paper fill or created "
    "a human-help request."
)
SUCCESS_CONDITIONS = frozenset(
    {
        "grounded_answer_delivered",
        "market_quote_delivered",
        "historical_return_calculated",
        "paper_fill_completed",
        "human_help_created",
    }
)
FAILURE_TYPES = frozenset(
    {
        "no_completed_action",
        "incomplete",
        "no_response",
        "tool_unavailable",
        "system_error",
    }
)
CHANNELS = frozenset({"browser", "sip"})
_CALL_ID = re.compile(r"^CALL-(?:[A-F0-9]{4}-){5}[A-F0-9]{4}$")


class CallAnalyticsValidationError(ValueError):
    """Raised before arbitrary or identifying values can enter analytics."""


def new_call_id() -> str:
    token = secrets.token_hex(12).upper()
    return "CALL-" + "-".join(token[index : index + 4] for index in range(0, 24, 4))


@dataclass(frozen=True)
class CallAnalyticsInput:
    call_id: str
    channel: str
    started_at: datetime
    ended_at: datetime
    success_condition: str | None = None
    failure_type: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.call_id, str)
            or _CALL_ID.fullmatch(self.call_id) is None
        ):
            raise CallAnalyticsValidationError("call_id is invalid.")
        if self.channel not in CHANNELS:
            raise CallAnalyticsValidationError("channel is invalid.")
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise CallAnalyticsValidationError("timestamps must include a timezone.")
        if self.ended_at < self.started_at:
            raise CallAnalyticsValidationError("ended_at cannot precede started_at.")
        if (
            self.success_condition is not None
            and self.success_condition not in SUCCESS_CONDITIONS
        ):
            raise CallAnalyticsValidationError("success_condition is invalid.")
        if self.failure_type is not None and self.failure_type not in FAILURE_TYPES:
            raise CallAnalyticsValidationError("failure_type is invalid.")
        if (self.success_condition is None) == (self.failure_type is None):
            raise CallAnalyticsValidationError(
                "Exactly one supported success or failure detail is required."
            )


class SQLiteCallAnalyticsStore:
    """Store minimal call outcomes and publish a caller-safe JSON snapshot."""

    def __init__(self, database_path: str | Path, *, snapshot_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._snapshot_path = Path(snapshot_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        if not self._snapshot_path.exists():
            self._write_snapshot(self.public_summary())

    def record(self, call: CallAnalyticsInput) -> None:
        if not isinstance(call, CallAnalyticsInput):
            raise CallAnalyticsValidationError("A call analytics record is required.")
        outcome = "successful" if call.success_condition is not None else "failed"
        detail = call.success_condition or call.failure_type
        duration_seconds = max(
            0, round((call.ended_at - call.started_at).total_seconds())
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO call_outcomes (
                    call_id, channel, started_at, ended_at, duration_seconds,
                    outcome, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call.call_id,
                    call.channel,
                    call.started_at.isoformat(),
                    call.ended_at.isoformat(),
                    duration_seconds,
                    outcome,
                    detail,
                ),
            )
        self._write_snapshot(self.public_summary())

    def public_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            total, successful, failed = connection.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN outcome = 'successful' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END)
                FROM call_outcomes
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT call_id, started_at, duration_seconds, channel, outcome, detail
                FROM call_outcomes
                ORDER BY started_at DESC, call_id DESC
                LIMIT 20
                """
            ).fetchall()
        total = int(total or 0)
        successful = int(successful or 0)
        failed = int(failed or 0)
        rate = round(successful * 100 / total, 1) if total else 0.0
        return {
            "version": 1,
            "success_definition": CALL_SUCCESS_DEFINITION,
            "totals": {
                "total_calls": total,
                "successful_calls": successful,
                "failed_calls": failed,
                "success_rate_percent": rate,
            },
            "recent_calls": [
                {
                    "call_id": row[0],
                    "started_at": row[1],
                    "duration_seconds": row[2],
                    "channel": row[3],
                    "outcome": row[4],
                    "detail": row[5],
                }
                for row in rows
            ],
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path, timeout=5)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS call_outcomes (
                    call_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    detail TEXT NOT NULL
                )
                """
            )

    def _write_snapshot(self, summary: dict[str, object]) -> None:
        payload = json.dumps(
            summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self._snapshot_path.parent,
            prefix=f".{self._snapshot_path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self._snapshot_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
