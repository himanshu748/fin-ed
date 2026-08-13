from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from fined.call_analytics import (
    CALL_SUCCESS_DEFINITION,
    CallAnalyticsInput,
    CallAnalyticsValidationError,
    SQLiteCallAnalyticsStore,
)

STARTED = datetime(2026, 8, 13, 4, 30, tzinfo=UTC)


def test_real_call_outcomes_update_private_sqlite_and_public_snapshot(tmp_path) -> None:
    # Catches dashboard counters being hardcoded or disconnected from ended calls.
    database = tmp_path / "analytics" / "fined.sqlite3"
    snapshot = tmp_path / "analytics" / "public-summary.json"
    store = SQLiteCallAnalyticsStore(database, snapshot_path=snapshot)

    store.record(
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED + timedelta(seconds=42),
            success_condition="market_quote_delivered",
        )
    )
    store.record(
        CallAnalyticsInput(
            call_id="CALL-1111-2222-3333-4444-5555-6666",
            channel="sip",
            started_at=STARTED + timedelta(minutes=1),
            ended_at=STARTED + timedelta(minutes=1, seconds=9),
            failure_type="incomplete",
        )
    )

    summary = store.public_summary()
    assert summary["success_definition"] == CALL_SUCCESS_DEFINITION
    assert summary["totals"] == {
        "total_calls": 2,
        "successful_calls": 1,
        "failed_calls": 1,
        "success_rate_percent": 50.0,
    }
    assert summary["recent_calls"] == [
        {
            "call_id": "CALL-1111-2222-3333-4444-5555-6666",
            "started_at": "2026-08-13T04:31:00+00:00",
            "duration_seconds": 9,
            "channel": "sip",
            "outcome": "failed",
            "detail": "incomplete",
        },
        {
            "call_id": "CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            "started_at": "2026-08-13T04:30:00+00:00",
            "duration_seconds": 42,
            "channel": "browser",
            "outcome": "successful",
            "detail": "market_quote_delivered",
        },
    ]
    assert json.loads(snapshot.read_text()) == summary

    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(call_outcomes)")
        }
    assert columns == {
        "call_id",
        "channel",
        "started_at",
        "ended_at",
        "duration_seconds",
        "outcome",
        "detail",
    }
    assert not columns & {"phone_number", "caller_id", "transcript", "room_name"}


def test_duplicate_shutdown_is_idempotent_and_invalid_outcomes_fail_closed(
    tmp_path,
) -> None:
    # Catches one LiveKit job being counted twice or arbitrary sensitive detail storage.
    store = SQLiteCallAnalyticsStore(
        tmp_path / "fined.sqlite3",
        snapshot_path=tmp_path / "public-summary.json",
    )
    record = CallAnalyticsInput(
        call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
        channel="browser",
        started_at=STARTED,
        ended_at=STARTED + timedelta(seconds=1),
        failure_type="no_completed_action",
    )

    store.record(record)
    store.record(record)

    assert store.public_summary()["totals"]["total_calls"] == 1  # type: ignore[index]
    with pytest.raises(CallAnalyticsValidationError):
        store.record(
            CallAnalyticsInput(
                call_id="CALL-FFFF-FFFF-FFFF-FFFF-FFFF-FFFF",
                channel="browser",
                started_at=STARTED,
                ended_at=STARTED,
                failure_type="OTP 123456",
            )
        )


def test_one_and_only_one_success_or_failure_detail_is_required() -> None:
    # Catches ambiguous analytics rows that could inflate both success and failure.
    with pytest.raises(CallAnalyticsValidationError):
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED,
        )
    with pytest.raises(CallAnalyticsValidationError):
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED,
            success_condition="grounded_answer_delivered",
            failure_type="incomplete",
        )
    with pytest.raises(CallAnalyticsValidationError):
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED,
            success_condition="OTP 123456",
            failure_type="incomplete",
        )
