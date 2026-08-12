from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from fined.outbound import (
    OUTBOUND_REMINDER_PAPER_PRACTICE,
    OutboundCallError,
    OutboundCallRequest,
    OutboundConfigurationError,
    build_outbound_greeting,
    build_outbound_metadata,
    classify_sip_failure,
    initiate_outbound_call,
    parse_outbound_metadata,
)


class FakeDispatchService:
    def __init__(self) -> None:
        self.requests: list[object] = []
        self.deleted: list[tuple[str, str]] = []

    async def create_dispatch(self, request: object) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(id="dispatch-123")

    async def delete_dispatch(self, dispatch_id: str, room_name: str) -> None:
        self.deleted.append((dispatch_id, room_name))


class FakeSIPService:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.requests: list[object] = []
        self.timeouts: list[float | None] = []

    async def create_sip_participant(
        self,
        request: object,
        *,
        timeout: float | None = None,
    ) -> SimpleNamespace:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(sip_call_id="call-123")


class FakeLiveKitAPI:
    def __init__(self, *, sip_failure: BaseException | None = None) -> None:
        self.agent_dispatch = FakeDispatchService()
        self.sip = FakeSIPService(failure=sip_failure)


def _request(**changes: object) -> OutboundCallRequest:
    fields: dict[str, object] = {
        "phone_number": "+919876543210",
        "sip_trunk_id": "ST_abc12345",
        "agent_name": "my-agent",
        "reminder": OUTBOUND_REMINDER_PAPER_PRACTICE,
    }
    fields.update(changes)
    return OutboundCallRequest(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"phone_number": "9876543210"},
        {"phone_number": "+9198765432100x"},
        {"sip_trunk_id": "not-a-livekit-trunk"},
        {"agent_name": "my agent"},
        {"reminder": "market_tip"},
    ],
)
def test_outbound_request_rejects_untrusted_contact_or_configuration(
    changes: dict[str, object],
) -> None:
    # Catches accidental dialing of a malformed number or an expanded call use case.
    with pytest.raises(OutboundConfigurationError):
        _request(**changes)


def test_outbound_metadata_is_allowlisted_and_never_contains_the_phone_number() -> None:
    # Catches a contact number leaking from the command boundary into job metadata.
    request = _request()
    metadata = build_outbound_metadata(request.reminder)

    assert json.loads(metadata) == {
        "kind": "fined_outbound_learning_reminder",
        "learning_mode": "stocks",
        "reminder": "paper_practice",
        "version": 1,
    }
    assert request.phone_number not in metadata
    assert parse_outbound_metadata(metadata) == request.reminder
    assert (
        parse_outbound_metadata(
            '{"version":1,"kind":"fined_outbound_learning_reminder",'
            '"reminder":"paper_practice","learning_mode":"stocks","to":"+919876543210"}'
        )
        is None
    )


def test_outbound_opening_states_identity_reason_and_stop_method_in_two_sentences() -> (
    None
):
    # Catches calls that omit the mandatory consent and opt-out disclosure.
    opening = build_outbound_greeting(OUTBOUND_REMINDER_PAPER_PRACTICE)

    assert opening == (
        "Hello, this is FinEd Saathi, calling because you opted in to a paper "
        "trading practice reminder. Say stop at any time and I will end this call."
    )
    assert len([sentence for sentence in opening.split(".") if sentence.strip()]) == 2


def test_consented_human_help_callback_has_a_distinct_private_dispatch_and_opening() -> (
    None
):
    # Catches a human-help callback being rejected or misrepresented as a human caller.
    request = _request(reminder="human_help_callback")

    assert json.loads(build_outbound_metadata(request.reminder)) == {
        "kind": "fined_outbound_learning_reminder",
        "learning_mode": "general",
        "reminder": "human_help_callback",
        "version": 1,
    }
    assert parse_outbound_metadata(build_outbound_metadata(request.reminder)) == (
        request.reminder
    )
    assert build_outbound_greeting(request.reminder) == (
        "Hello, this is FinEd Saathi, making the automated callback you requested "
        "about your human-help request. This is not a human adviser, and you can say "
        "stop at any time to end this call."
    )


@pytest.mark.asyncio
async def test_outbound_call_dispatches_then_dials_without_contact_metadata() -> None:
    # Catches a dial before the named worker is dispatched or a metadata privacy leak.
    client = FakeLiveKitAPI()
    request = _request()
    identifiers = iter(("roomtoken", "callertoken"))

    result = await initiate_outbound_call(
        client,
        request,
        token_factory=lambda: next(identifiers),
    )

    assert result.room_name == "fined-outbound-roomtoken"
    assert result.participant_identity == "outbound-recipient-callertoken"
    assert result.sip_call_id == "call-123"
    assert request.phone_number not in repr(result)

    dispatch_request = client.agent_dispatch.requests[0]
    assert dispatch_request.agent_name == "my-agent"  # type: ignore[attr-defined]
    assert dispatch_request.room == result.room_name  # type: ignore[attr-defined]
    assert request.phone_number not in dispatch_request.metadata  # type: ignore[attr-defined]
    assert parse_outbound_metadata(dispatch_request.metadata) == request.reminder  # type: ignore[attr-defined]

    sip_request = client.sip.requests[0]
    assert sip_request.sip_trunk_id == "ST_abc12345"  # type: ignore[attr-defined]
    assert sip_request.sip_call_to == request.phone_number  # type: ignore[attr-defined]
    assert sip_request.room_name == result.room_name  # type: ignore[attr-defined]
    assert sip_request.participant_identity == result.participant_identity  # type: ignore[attr-defined]
    assert sip_request.participant_name == "FinEd Saathi learner"  # type: ignore[attr-defined]
    assert sip_request.wait_until_answered is True  # type: ignore[attr-defined]
    assert sip_request.krisp_enabled is True  # type: ignore[attr-defined]
    assert sip_request.ringing_timeout.seconds == 25  # type: ignore[attr-defined]
    assert sip_request.max_call_duration.seconds == 300  # type: ignore[attr-defined]
    assert client.sip.timeouts == [27.0]
    assert client.agent_dispatch.deleted == []


@pytest.mark.asyncio
async def test_outbound_dial_failure_cleans_up_dispatch_and_hides_phone_number() -> (
    None
):
    # Catches stranded jobs, automatic retries, and contact disclosure in failures.
    client = FakeLiveKitAPI(sip_failure=RuntimeError("provider says +919876543210"))
    request = _request()

    with pytest.raises(OutboundCallError) as failure:
        await initiate_outbound_call(
            client,
            request,
            token_factory=lambda: "testtoken",
        )

    assert failure.value.outcome == "failed"
    assert "+919876543210" not in str(failure.value)
    assert client.agent_dispatch.deleted == [
        ("dispatch-123", "fined-outbound-testtoken")
    ]
    assert len(client.sip.requests) == 1


@pytest.mark.asyncio
async def test_outbound_cancellation_still_cleans_up_the_created_dispatch() -> None:
    # Catches a cancelled operator command leaving an active worker dispatch behind.
    client = FakeLiveKitAPI(sip_failure=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await initiate_outbound_call(
            client,
            _request(),
            token_factory=lambda: "testtoken",
        )

    assert client.agent_dispatch.deleted == [
        ("dispatch-123", "fined-outbound-testtoken")
    ]


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(486, "busy"), (408, "not_answered"), (480, "not_answered"), (500, "failed")],
)
def test_sip_failure_outcomes_are_safe_and_do_not_retry(
    status_code: int, expected: str
) -> None:
    # Catches opaque outbound results and a later accidental retry policy.
    assert classify_sip_failure(status_code) == expected
