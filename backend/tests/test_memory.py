from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fined.memory import (
    CallerMemoryInput,
    MemoryConsentRequiredError,
    MemoryValidationError,
    SQLiteCallerMemoryStore,
)


def _memory_input(**changes: object) -> CallerMemoryInput:
    fields: dict[str, object] = {
        "caller_id": "learner-7",
        "name": "Himanshu",
        "language_preference": "bilingual",
        "facts": {
            "experience_level": "beginner",
            "learning_goal": "understand ETFs before using paper practice",
        },
    }
    fields.update(changes)
    return CallerMemoryInput(**fields)  # type: ignore[arg-type]


def test_consented_memory_survives_store_recreation(tmp_path) -> None:
    # Catches in-memory-only persistence and loss of safe learning context.
    database = tmp_path / "memory" / "fined.sqlite3"
    saved_at = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    first_store = SQLiteCallerMemoryStore(database, clock=lambda: saved_at)

    saved = first_store.save(_memory_input(), consent_confirmed=True)
    reloaded = SQLiteCallerMemoryStore(database).lookup("learner-7")

    assert saved == reloaded
    assert reloaded is not None
    assert reloaded.name == "Himanshu"
    assert reloaded.language_preference == "bilingual"
    assert reloaded.facts == {
        "experience_level": "beginner",
        "learning_goal": "understand ETFs before using paper practice",
    }
    assert reloaded.last_interaction == saved_at


def test_save_without_explicit_consent_writes_nothing(tmp_path) -> None:
    # Catches any path that persists financial-learning facts before consent.
    store = SQLiteCallerMemoryStore(tmp_path / "fined.sqlite3")

    with pytest.raises(MemoryConsentRequiredError):
        store.save(_memory_input(), consent_confirmed=False)

    assert store.lookup("learner-7") is None


@pytest.mark.parametrize(
    "facts",
    [
        {"account_number": "123456789012", "learning_goal": "learn ETFs"},
        {"experience_level": "beginner"},
        {
            "experience_level": "beginner",
            "learning_goal": "my PAN is ABCDE1234F",
        },
    ],
)
def test_memory_rejects_unsafe_or_incomplete_fact_sets(tmp_path, facts) -> None:
    # Catches storage of financial identifiers or fewer than two safe facts.
    store = SQLiteCallerMemoryStore(tmp_path / "fined.sqlite3")

    with pytest.raises(MemoryValidationError):
        store.save(_memory_input(facts=facts), consent_confirmed=True)

    assert store.lookup("learner-7") is None


def test_forget_requires_consent_and_removes_the_persisted_record(tmp_path) -> None:
    # Catches silent deletion and incomplete forget-me behavior.
    store = SQLiteCallerMemoryStore(tmp_path / "fined.sqlite3")
    store.save(_memory_input(), consent_confirmed=True)

    with pytest.raises(MemoryConsentRequiredError):
        store.forget("learner-7", consent_confirmed=False)
    assert store.lookup("learner-7") is not None

    assert store.forget("learner-7", consent_confirmed=True) is True
    assert store.lookup("learner-7") is None
