from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime

import pytest

from fined.escalations import (
    EscalationConsentRequiredError,
    EscalationRequestInput,
    EscalationValidationError,
    SQLiteEscalationStore,
)


def _request(**changes: object) -> EscalationRequestInput:
    fields: dict[str, object] = {
        "anonymous_caller_id": "learner-7",
        "reason": "suspected_fraud",
        "urgency": "high",
        "caller_language": "bilingual",
        "summary": "Caller reports an unfamiliar transfer in the broker app.",
        "checks": (
            "Asked caller to stop sharing credentials.",
            "Advised contacting the broker through its official support channel.",
        ),
        "follow_up": "in_app",
    }
    fields.update(changes)
    return EscalationRequestInput(**fields)  # type: ignore[arg-type]


def test_consented_escalation_survives_store_recreation(tmp_path) -> None:
    # Catches an in-memory request queue and leakage of the private caller identifier.
    database = tmp_path / "escalations" / "fined.sqlite3"
    created_at = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
    store = SQLiteEscalationStore(
        database,
        clock=lambda: created_at,
        token_factory=lambda: "a1b2c3d4e5f60123456789ab",
    )

    saved = store.create(_request(), consent_confirmed=True)
    reloaded = SQLiteEscalationStore(database).list_open()

    assert reloaded == [saved]
    assert saved.reference_id == "HELP-A1B2-C3D4-E5F6-0123-4567-89AB"
    assert re.fullmatch(r"HELP-(?:[A-F0-9]{4}-){5}[A-F0-9]{4}", saved.reference_id)
    assert saved.created_at == created_at
    assert saved.status == "open"
    assert not hasattr(saved, "anonymous_caller_id")


def test_sensitive_values_are_redacted_before_an_escalation_is_persisted(
    tmp_path,
) -> None:
    # Catches OTPs, PINs, passwords, PANs, Aadhaar IDs, and long account runs
    # leaking into the limited human-review record.
    database = tmp_path / "fined.sqlite3"
    store = SQLiteEscalationStore(
        database,
        token_factory=lambda: "deadbeef0011223344556677",
    )
    unsafe = _request(
        summary=(
            "Caller gave OTP 123456, PIN: 4321, password: sunflower, PAN "
            "ABCDE1234F, Aadhaar 1234 5678 9012, and account 12345678."
        ),
        checks=("Asked them not to share password: sunflower again.",),
    )

    saved = store.create(unsafe, consent_confirmed=True)

    for sensitive_value in (
        "123456",
        "4321",
        "sunflower",
        "ABCDE1234F",
        "1234 5678 9012",
        "12345678",
    ):
        assert sensitive_value not in saved.summary
        assert all(sensitive_value not in check for check in saved.checks)
    assert "[REDACTED]" in saved.summary
    with sqlite3.connect(database) as connection:
        persisted = connection.execute(
            "SELECT summary, checks_json FROM escalation_requests"
        ).fetchone()
    assert persisted is not None
    assert "12345678" not in " ".join(persisted)


def test_redaction_covers_common_sensitive_value_variants(tmp_path) -> None:
    # Catches alternative labels, formatting, and quoted secrets bypassing redaction.
    store = SQLiteEscalationStore(
        tmp_path / "fined.sqlite3",
        token_factory=lambda: "abcdef0123456789abcdef01",
    )
    saved = store.create(
        _request(
            summary=(
                'OTP code is 654321; PIN code: 1122; password: "two word '
                'secret"; PAN abcde1234f; Aadhaar 1234-5678-9012; account '
                "number 12,345,678."
            ),
            checks=("Do not share PIN code 2468 or account 1234.5678.",),
        ),
        consent_confirmed=True,
    )

    public_text = " ".join((saved.summary, *saved.checks))
    for sensitive_value in (
        "654321",
        "1122",
        "two word secret",
        "abcde1234f",
        "1234-5678-9012",
        "12,345,678",
        "2468",
        "1234.5678",
    ):
        assert sensitive_value.casefold() not in public_text.casefold()


def test_missing_explicit_consent_leaves_no_escalation_row(tmp_path) -> None:
    # Catches even a temporary human-help record being written before a current yes.
    store = SQLiteEscalationStore(tmp_path / "fined.sqlite3")

    with pytest.raises(EscalationConsentRequiredError):
        store.create(_request(), consent_confirmed=False)

    assert store.list_open() == []


def test_matching_open_escalation_is_deduplicated_for_the_anonymous_caller(
    tmp_path,
) -> None:
    # Catches a repeated consent turn creating a second human-help request.
    tokens = iter(("00112233445566778899aabb", "ffeeddccbbaa998877665544"))
    store = SQLiteEscalationStore(
        tmp_path / "fined.sqlite3",
        token_factory=lambda: next(tokens),
    )

    first = store.create(_request(), consent_confirmed=True)
    duplicate = store.create(_request(), consent_confirmed=True)

    assert duplicate == first
    assert store.list_open() == [first]


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "normal_question"},
        {"urgency": "medium"},
        {"reason": "decision_review", "urgency": "emergency"},
        {"caller_language": "hinglish"},
        {"follow_up": "email"},
        {"summary": "x" * 481},
        {"checks": ()},
        {"checks": ("one", "two", "three", "four", "five")},
        {"checks": "a plain string is not a list of checks"},
        {"anonymous_caller_id": " learner-7"},
    ],
)
def test_store_rejects_fields_outside_the_limited_escalation_schema(
    tmp_path, changes: dict[str, object]
) -> None:
    # Catches an expanded support queue, unsafe urgency, or unbounded content.
    store = SQLiteEscalationStore(tmp_path / "fined.sqlite3")

    with pytest.raises(EscalationValidationError):
        store.create(_request(**changes), consent_confirmed=True)

    assert store.list_open() == []
