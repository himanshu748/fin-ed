"""Privacy-safe call outcomes and a public aggregate dashboard snapshot."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CALL_SUCCESS_DEFINITION = (
    "The learner completed a verified action: received grounded market evidence, "
    "received a verified tax rule, received trusted market or historical data, "
    "completed a paper fill or created a human-help request."
)
SUCCESS_CONDITIONS = frozenset(
    {
        "grounded_answer_delivered",
        "tax_rule_delivered",
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
_AGENT_STATES = frozenset({"initializing", "idle", "listening", "thinking", "speaking"})


class CallAnalyticsValidationError(ValueError):
    """Raised before arbitrary or identifying values can enter analytics."""


class AgentTalkTimeTracker:
    """Measure only validated LiveKit agent-speaking state intervals."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._totals = {"fined": 0.0, "taxed": 0.0}
        self._open_interval: tuple[str, float] | None = None
        self._closed = False

    def on_agent_state_changed(
        self, old_state: str, new_state: str, active_agent_name: object
    ) -> None:
        if self._closed:
            return
        if old_state not in _AGENT_STATES or new_state not in _AGENT_STATES:
            self._open_interval = None
            return
        if old_state == new_state:
            self._open_interval = None
            return
        if new_state == "speaking":
            if old_state == "speaking" or self._open_interval is not None:
                self._open_interval = None
                return
            if (
                not isinstance(active_agent_name, str)
                or active_agent_name not in self._totals
            ):
                return
            self._open_interval = (str(active_agent_name), self._clock())
            return
        if old_state == "speaking":
            self._close_open_interval()
            return
        if self._open_interval is not None:
            self._open_interval = None

    def close(self) -> dict[str, int]:
        if not self._closed:
            self._close_open_interval()
            self._closed = True
        return {
            "fined_talk_seconds": round(self._totals["fined"]),
            "taxed_talk_seconds": round(self._totals["taxed"]),
        }

    def _close_open_interval(self) -> None:
        interval = self._open_interval
        self._open_interval = None
        if interval is None:
            return
        agent_name, started_at = interval
        ended_at = self._clock()
        if ended_at < started_at:
            return
        self._totals[agent_name] += ended_at - started_at


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
    fined_talk_seconds: int = 0
    taxed_talk_seconds: int = 0
    handoff_count: int = 0

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
        measurements = (
            self.fined_talk_seconds,
            self.taxed_talk_seconds,
            self.handoff_count,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in measurements
        ):
            raise CallAnalyticsValidationError(
                "Agent measurements must be non-negative integers."
            )
        duration_seconds = round((self.ended_at - self.started_at).total_seconds())
        if self.fined_talk_seconds + self.taxed_talk_seconds > duration_seconds + 1:
            raise CallAnalyticsValidationError(
                "Agent speaking time cannot exceed call duration."
            )


class SQLiteCallAnalyticsStore:
    """Store minimal call outcomes and publish a caller-safe JSON snapshot."""

    def __init__(self, database_path: str | Path, *, snapshot_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._snapshot_path = Path(snapshot_path)
        self._snapshot_lock_path = self._snapshot_path.with_name(
            f".{self._snapshot_path.name}.lock"
        )
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        with self._publication_lock():
            self._write_snapshot(self.public_summary())

    def record(self, call: CallAnalyticsInput) -> None:
        if not isinstance(call, CallAnalyticsInput):
            raise CallAnalyticsValidationError("A call analytics record is required.")
        outcome = "successful" if call.success_condition is not None else "failed"
        detail = call.success_condition or call.failure_type
        duration_seconds = max(
            0, round((call.ended_at - call.started_at).total_seconds())
        )
        with self._publication_lock():
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO call_outcomes (
                        call_id, channel, started_at, ended_at, duration_seconds,
                        outcome, detail, fined_talk_seconds, taxed_talk_seconds,
                        handoff_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call.call_id,
                        call.channel,
                        call.started_at.isoformat(),
                        call.ended_at.isoformat(),
                        duration_seconds,
                        outcome,
                        detail,
                        call.fined_talk_seconds,
                        call.taxed_talk_seconds,
                        call.handoff_count,
                    ),
                )
            self._write_snapshot(self.public_summary())

    def public_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            (
                total,
                successful,
                failed,
                total_duration,
                fined_talk,
                taxed_talk,
                handoffs,
            ) = connection.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN outcome = 'successful' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END),
                       SUM(duration_seconds),
                       SUM(fined_talk_seconds),
                       SUM(taxed_talk_seconds),
                       SUM(handoff_count)
                FROM call_outcomes
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT call_id, started_at, duration_seconds, channel, outcome, detail,
                       fined_talk_seconds, taxed_talk_seconds, handoff_count
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
            "version": 2,
            "success_definition": CALL_SUCCESS_DEFINITION,
            "totals": {
                "total_calls": total,
                "successful_calls": successful,
                "failed_calls": failed,
                "success_rate_percent": rate,
                "total_duration_seconds": int(total_duration or 0),
                "fined_talk_seconds": int(fined_talk or 0),
                "taxed_talk_seconds": int(taxed_talk or 0),
                "handoff_count": int(handoffs or 0),
            },
            "recent_calls": [
                {
                    "call_id": row[0],
                    "started_at": row[1],
                    "duration_seconds": row[2],
                    "channel": row[3],
                    "outcome": row[4],
                    "detail": row[5],
                    "fined_talk_seconds": row[6],
                    "taxed_talk_seconds": row[7],
                    "handoff_count": row[8],
                }
                for row in rows
            ],
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path, timeout=5)

    def _initialize(self) -> None:
        with self._connect() as connection:
            self._enable_write_ahead_log(connection)
            connection.execute("BEGIN IMMEDIATE")
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
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(call_outcomes)")
            }
            for column in (
                "fined_talk_seconds",
                "taxed_talk_seconds",
                "handoff_count",
            ):
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE call_outcomes "
                        f"ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                    )

    @staticmethod
    def _enable_write_ahead_log(connection: sqlite3.Connection) -> None:
        retry_delays = (0.025, 0.05, 0.1, 0.2, 0.4)
        for retry_delay in (*retry_delays, None):
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).casefold() or retry_delay is None:
                    raise
                time.sleep(retry_delay)

    @contextmanager
    def _publication_lock(self) -> Iterator[None]:
        file_descriptor = os.open(
            self._snapshot_lock_path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        with os.fdopen(file_descriptor, "rb+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
