from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from threading import Barrier, BrokenBarrierError, Event

import pytest

from fined.call_analytics import (
    CALL_SUCCESS_DEFINITION,
    AgentTalkTimeTracker,
    CallAnalyticsInput,
    CallAnalyticsValidationError,
    SQLiteCallAnalyticsStore,
)

STARTED = datetime(2026, 8, 13, 4, 30, tzinfo=UTC)


class FakeMonotonicClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_agent_talk_time_tracks_valid_intervals_and_closes_at_shutdown() -> None:
    # Catches transcript or voice-label inference replacing state-backed interval timing.
    clock = FakeMonotonicClock()
    tracker = AgentTalkTimeTracker(clock=clock)

    tracker.on_agent_state_changed("listening", "speaking", "fined")
    clock.advance(2.6)
    tracker.on_agent_state_changed("speaking", "thinking", "fined")
    tracker.on_agent_state_changed("thinking", "speaking", "taxed")
    clock.advance(1.6)

    assert tracker.close() == {
        "fined_talk_seconds": 3,
        "taxed_talk_seconds": 2,
    }
    assert tracker.close() == {
        "fined_talk_seconds": 3,
        "taxed_talk_seconds": 2,
    }


def test_agent_talk_time_fails_closed_on_unknown_labels_and_invalid_transitions() -> (
    None
):
    # Catches unknown agents or duplicate transitions being charged to a known specialist.
    clock = FakeMonotonicClock()
    tracker = AgentTalkTimeTracker(clock=clock)

    tracker.on_agent_state_changed("listening", "speaking", "mystery")
    clock.advance(8)
    tracker.on_agent_state_changed("speaking", "listening", "mystery")
    tracker.on_agent_state_changed("listening", "speaking", "fined")
    clock.advance(4)
    tracker.on_agent_state_changed("speaking", "speaking", "fined")
    clock.advance(5)
    tracker.on_agent_state_changed("speaking", "listening", "fined")

    assert tracker.close() == {
        "fined_talk_seconds": 0,
        "taxed_talk_seconds": 0,
    }


def test_agent_talk_time_rejects_unknown_livekit_states_and_malformed_labels() -> None:
    # Catches corrupted state events opening an interval under a valid-looking label.
    clock = FakeMonotonicClock()
    tracker = AgentTalkTimeTracker(clock=clock)

    tracker.on_agent_state_changed("unknown", "speaking", "fined")
    clock.advance(2)
    tracker.on_agent_state_changed("speaking", "listening", "fined")
    tracker.on_agent_state_changed("listening", "speaking", ["fined"])
    clock.advance(2)
    tracker.on_agent_state_changed("speaking", "listening", ["fined"])

    assert tracker.close() == {
        "fined_talk_seconds": 0,
        "taxed_talk_seconds": 0,
    }


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
            fined_talk_seconds=20,
            taxed_talk_seconds=12,
            handoff_count=2,
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
        "total_duration_seconds": 51,
        "fined_talk_seconds": 20,
        "taxed_talk_seconds": 12,
        "handoff_count": 2,
    }
    assert summary["recent_calls"] == [
        {
            "call_id": "CALL-1111-2222-3333-4444-5555-6666",
            "started_at": "2026-08-13T04:31:00+00:00",
            "duration_seconds": 9,
            "channel": "sip",
            "outcome": "failed",
            "detail": "incomplete",
            "fined_talk_seconds": 0,
            "taxed_talk_seconds": 0,
            "handoff_count": 0,
        },
        {
            "call_id": "CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            "started_at": "2026-08-13T04:30:00+00:00",
            "duration_seconds": 42,
            "channel": "browser",
            "outcome": "successful",
            "detail": "market_quote_delivered",
            "fined_talk_seconds": 20,
            "taxed_talk_seconds": 12,
            "handoff_count": 2,
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
        "fined_talk_seconds",
        "taxed_talk_seconds",
        "handoff_count",
    }
    assert not columns & {
        "phone_number",
        "caller_id",
        "transcript",
        "room_name",
        "identity",
        "audio",
        "question",
        "voice_provider",
    }


def test_tax_rule_success_is_fixed_and_stores_no_tax_question_or_source(
    tmp_path,
) -> None:
    # Catches verified TaxEd outcomes leaking a learner question or registry record.
    database = tmp_path / "fined.sqlite3"
    store = SQLiteCallAnalyticsStore(
        database, snapshot_path=tmp_path / "public-summary.json"
    )

    store.record(
        CallAnalyticsInput(
            call_id="CALL-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED + timedelta(seconds=10),
            success_condition="tax_rule_delivered",
            fined_talk_seconds=3,
            taxed_talk_seconds=6,
            handoff_count=1,
        )
    )

    summary = store.public_summary()
    assert summary["version"] == 2
    assert summary["recent_calls"][0]["detail"] == "tax_rule_delivered"  # type: ignore[index]
    serialized = json.dumps(summary)
    for forbidden in ("question", "asset", "amount", "source_url"):
        assert forbidden not in serialized


def test_existing_version_one_table_migrates_speaking_fields_as_zero(tmp_path) -> None:
    # Catches additive migration dropping old outcomes or returning null measurements.
    database = tmp_path / "fined.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE call_outcomes (
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
        connection.execute(
            """
            INSERT INTO call_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CALL-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
                "browser",
                STARTED.isoformat(),
                (STARTED + timedelta(seconds=7)).isoformat(),
                7,
                "failed",
                "incomplete",
            ),
        )

    summary = SQLiteCallAnalyticsStore(
        database, snapshot_path=tmp_path / "public-summary.json"
    ).public_summary()

    assert summary["totals"] == {
        "total_calls": 1,
        "successful_calls": 0,
        "failed_calls": 1,
        "success_rate_percent": 0.0,
        "total_duration_seconds": 7,
        "fined_talk_seconds": 0,
        "taxed_talk_seconds": 0,
        "handoff_count": 0,
    }
    assert summary["recent_calls"][0]["fined_talk_seconds"] == 0  # type: ignore[index]
    assert summary["recent_calls"][0]["taxed_talk_seconds"] == 0  # type: ignore[index]
    assert summary["recent_calls"][0]["handoff_count"] == 0  # type: ignore[index]


def test_concurrent_constructors_serialize_one_complete_v1_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Catches two rollout jobs racing from the same legacy schema observation.
    database = tmp_path / "fined.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE call_outcomes (
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
        connection.execute(
            "INSERT INTO call_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "CALL-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
                "browser",
                STARTED.isoformat(),
                (STARTED + timedelta(seconds=7)).isoformat(),
                7,
                "failed",
                "incomplete",
            ),
        )

    real_connect = sqlite3.connect
    schema_read_barrier = Barrier(2)

    class CoordinatedConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self._connection.__exit__(*args)

        def execute(self, statement: str, *args: object):
            if statement.strip().startswith("PRAGMA table_info"):
                with suppress(BrokenBarrierError):
                    schema_read_barrier.wait(timeout=0.25)
            return self._connection.execute(statement, *args)

    def coordinated_connect(*args: object, **kwargs: object) -> CoordinatedConnection:
        return CoordinatedConnection(real_connect(*args, **kwargs))

    monkeypatch.setattr("fined.call_analytics.sqlite3.connect", coordinated_connect)
    constructor_barrier = Barrier(2)

    def construct(index: int) -> SQLiteCallAnalyticsStore:
        constructor_barrier.wait(timeout=2)
        return SQLiteCallAnalyticsStore(
            database, snapshot_path=tmp_path / f"summary-{index}.json"
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        stores = [executor.submit(construct, index) for index in range(2)]
        assert all(
            future.result(timeout=5).public_summary()["version"] == 2
            for future in stores
        )

    with real_connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(call_outcomes)")
        }
        old_row = connection.execute(
            """
            SELECT call_id, duration_seconds, fined_talk_seconds,
                   taxed_talk_seconds, handoff_count
            FROM call_outcomes
            """
        ).fetchone()
    assert columns == {
        "call_id",
        "channel",
        "started_at",
        "ended_at",
        "duration_seconds",
        "outcome",
        "detail",
        "fined_talk_seconds",
        "taxed_talk_seconds",
        "handoff_count",
    }
    assert old_row == (
        "CALL-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
        7,
        0,
        0,
        0,
    )


def test_two_writers_cannot_publish_an_older_database_view(tmp_path) -> None:
    # Catches a delayed writer replacing a newer atomic snapshot with stale totals.
    database = tmp_path / "fined.sqlite3"
    snapshot = tmp_path / "public-summary.json"
    first_store = SQLiteCallAnalyticsStore(database, snapshot_path=snapshot)
    second_store = SQLiteCallAnalyticsStore(database, snapshot_path=snapshot)
    stale_summary_ready = Event()
    allow_stale_publication = Event()
    second_writer_finished = Event()
    original_write_snapshot = first_store._write_snapshot

    def delay_first_snapshot(summary: dict[str, object]) -> None:
        stale_summary_ready.set()
        assert allow_stale_publication.wait(timeout=5)
        original_write_snapshot(summary)

    first_store._write_snapshot = delay_first_snapshot  # type: ignore[method-assign]
    first_call = CallAnalyticsInput(
        call_id="CALL-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
        channel="browser",
        started_at=STARTED,
        ended_at=STARTED + timedelta(seconds=7),
        failure_type="incomplete",
    )
    second_call = CallAnalyticsInput(
        call_id="CALL-1111-2222-3333-4444-5555-6666",
        channel="browser",
        started_at=STARTED + timedelta(minutes=1),
        ended_at=STARTED + timedelta(minutes=1, seconds=8),
        success_condition="tax_rule_delivered",
    )

    def record_second() -> None:
        second_store.record(second_call)
        second_writer_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_store.record, first_call)
        assert stale_summary_ready.wait(timeout=2)
        second_future = executor.submit(record_second)
        second_overtook_first = second_writer_finished.wait(timeout=0.5)
        allow_stale_publication.set()
        first_future.result(timeout=5)
        second_future.result(timeout=5)

    assert second_overtook_first is False
    assert json.loads(snapshot.read_text()) == first_store.public_summary()


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


@pytest.mark.parametrize(
    ("fined_talk_seconds", "taxed_talk_seconds", "handoff_count"),
    [
        (-1, 0, 0),
        (0, -1, 0),
        (0, 0, -1),
        (1.5, 0, 0),
        (0, 1.5, 0),
        (0, 0, 1.5),
        (True, 0, 0),
    ],
)
def test_agent_measurements_require_non_negative_integers(
    fined_talk_seconds: object,
    taxed_talk_seconds: object,
    handoff_count: object,
) -> None:
    # Catches malformed measurements entering the public summary.
    with pytest.raises(CallAnalyticsValidationError):
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED + timedelta(seconds=5),
            failure_type="incomplete",
            fined_talk_seconds=fined_talk_seconds,  # type: ignore[arg-type]
            taxed_talk_seconds=taxed_talk_seconds,  # type: ignore[arg-type]
            handoff_count=handoff_count,  # type: ignore[arg-type]
        )


def test_agent_speaking_sum_allows_only_one_rounding_second() -> None:
    # Catches impossible speaking time that exceeds the call measurement.
    CallAnalyticsInput(
        call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
        channel="browser",
        started_at=STARTED,
        ended_at=STARTED + timedelta(seconds=5),
        failure_type="incomplete",
        fined_talk_seconds=3,
        taxed_talk_seconds=3,
    )
    with pytest.raises(CallAnalyticsValidationError):
        CallAnalyticsInput(
            call_id="CALL-A1B2-C3D4-E5F6-0123-4567-89AB",
            channel="browser",
            started_at=STARTED,
            ended_at=STARTED + timedelta(seconds=5),
            failure_type="incomplete",
            fined_talk_seconds=4,
            taxed_talk_seconds=3,
        )
