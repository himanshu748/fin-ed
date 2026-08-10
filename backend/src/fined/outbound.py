"""Consent-bound outbound learning calls with no broker or browser access."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from google.protobuf.duration_pb2 import Duration
from livekit import api

from fined.modes import LearningMode

OUTBOUND_DISPATCH_KIND = "fined_outbound_learning_reminder"
OUTBOUND_METADATA_VERSION = 1
OUTBOUND_REMINDER_PAPER_PRACTICE = "paper_practice"
OUTBOUND_RINGING_TIMEOUT_SECONDS = 25
OUTBOUND_MAX_CALL_DURATION_SECONDS = 300
OUTBOUND_DIAL_TIMEOUT_SECONDS = 27.0
OUTBOUND_RECIPIENT_JOIN_TIMEOUT_SECONDS = 35.0
_E164_PHONE_NUMBER = re.compile(r"^\+[1-9][0-9]{7,14}$")
_SIP_TRUNK_ID = re.compile(r"^ST_[A-Za-z0-9_-]{6,128}$")
_AGENT_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_TOKEN = re.compile(r"^[a-z0-9]{8,64}$")


class OutboundConfigurationError(ValueError):
    """Raised before a call when its private explicit configuration is invalid."""


class OutboundCallError(RuntimeError):
    """A safe, non-sensitive outcome from a failed carrier dial attempt."""

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        super().__init__(f"Outbound call could not be started: {outcome}.")


@dataclass(frozen=True)
class OutboundReminder:
    """A small allowlisted purpose for an explicit opt-in learning call."""

    name: str
    learning_mode: LearningMode


PAPER_PRACTICE_REMINDER = OutboundReminder(
    name=OUTBOUND_REMINDER_PAPER_PRACTICE,
    learning_mode=LearningMode.STOCKS,
)


@dataclass(frozen=True)
class OutboundCallRequest:
    """Operator-supplied input. The phone number never enters dispatch metadata."""

    phone_number: str
    sip_trunk_id: str
    agent_name: str
    reminder: OutboundReminder | str

    def __post_init__(self) -> None:
        _validate_phone_number(self.phone_number)
        _validate_sip_trunk_id(self.sip_trunk_id)
        _validate_agent_name(self.agent_name)
        object.__setattr__(self, "reminder", _normalize_reminder(self.reminder))


@dataclass(frozen=True)
class OutboundCallResult:
    """Non-sensitive identifiers useful for a local operator acknowledgement."""

    room_name: str
    participant_identity: str
    sip_call_id: str | None


class _AgentDispatchService(Protocol):
    async def create_dispatch(
        self, request: api.CreateAgentDispatchRequest
    ) -> object: ...

    async def delete_dispatch(self, dispatch_id: str, room_name: str) -> object: ...


class _SIPService(Protocol):
    async def create_sip_participant(
        self,
        request: api.CreateSIPParticipantRequest,
        *,
        timeout: float | None = None,
    ) -> object: ...


class LiveKitOutboundAPI(Protocol):
    agent_dispatch: _AgentDispatchService
    sip: _SIPService


def build_outbound_metadata(reminder: OutboundReminder | str) -> str:
    """Create the complete, phone-free metadata allowlist for an agent dispatch."""
    reminder = _normalize_reminder(reminder)
    return json.dumps(
        {
            "version": OUTBOUND_METADATA_VERSION,
            "kind": OUTBOUND_DISPATCH_KIND,
            "reminder": PAPER_PRACTICE_REMINDER.name,
            "learning_mode": PAPER_PRACTICE_REMINDER.learning_mode.value,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_outbound_metadata(metadata: object) -> OutboundReminder | None:
    """Accept only the server-created outbound dispatch shape, never contact data."""
    if not isinstance(metadata, str) or not metadata:
        return None
    try:
        value = json.loads(metadata)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {
        "version",
        "kind",
        "reminder",
        "learning_mode",
    }:
        return None
    if value != {
        "version": OUTBOUND_METADATA_VERSION,
        "kind": OUTBOUND_DISPATCH_KIND,
        "reminder": PAPER_PRACTICE_REMINDER.name,
        "learning_mode": PAPER_PRACTICE_REMINDER.learning_mode.value,
    }:
        return None
    return PAPER_PRACTICE_REMINDER


def build_outbound_greeting(reminder: OutboundReminder | str) -> str:
    """Use a deterministic two-sentence disclosure before any conversation."""
    _normalize_reminder(reminder)
    return (
        "Hello, this is FinEd Saathi, calling because you opted in to a paper "
        "trading practice reminder. Say stop at any time and I will end this call."
    )


def classify_sip_failure(sip_status_code: int | None) -> str:
    """Return a small outcome vocabulary and deliberately never retry."""
    if sip_status_code == 486:
        return "busy"
    if sip_status_code in {408, 480}:
        return "not_answered"
    return "failed"


async def initiate_outbound_call(
    client: LiveKitOutboundAPI,
    request: OutboundCallRequest,
    *,
    token_factory: Callable[[], str] = lambda: secrets.token_hex(8),
) -> OutboundCallResult:
    """Dispatch the named agent then make one bounded dial attempt.

    The call is deliberately operator-triggered. It does not persist a number,
    schedule a retry, or expose a broker, paper-trading, or browser control path.
    """
    room_name = f"fined-outbound-{_new_token(token_factory)}"
    participant_identity = f"outbound-recipient-{_new_token(token_factory)}"
    dispatch = await client.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name=request.agent_name,
            room=room_name,
            metadata=build_outbound_metadata(request.reminder),
        )
    )
    dispatch_id = getattr(dispatch, "id", "")
    if not isinstance(dispatch_id, str) or not dispatch_id:
        raise OutboundCallError("failed")

    try:
        participant = await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=request.sip_trunk_id,
                sip_call_to=request.phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name="FinEd Saathi learner",
                ringing_timeout=Duration(seconds=OUTBOUND_RINGING_TIMEOUT_SECONDS),
                max_call_duration=Duration(seconds=OUTBOUND_MAX_CALL_DURATION_SECONDS),
                krisp_enabled=True,
                wait_until_answered=True,
            ),
            timeout=OUTBOUND_DIAL_TIMEOUT_SECONDS,
        )
    except BaseException as error:
        await _delete_dispatch_safely(client, dispatch_id, room_name)
        if not isinstance(error, Exception):
            raise
        raise OutboundCallError(
            classify_sip_failure(getattr(error, "sip_status_code", None))
        ) from None

    sip_call_id = getattr(participant, "sip_call_id", None)
    return OutboundCallResult(
        room_name=room_name,
        participant_identity=participant_identity,
        sip_call_id=sip_call_id
        if isinstance(sip_call_id, str) and sip_call_id
        else None,
    )


def _new_token(token_factory: Callable[[], str]) -> str:
    token = token_factory()
    if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
        raise OutboundConfigurationError("Could not create a safe outbound identifier.")
    return token


async def _delete_dispatch_safely(
    client: LiveKitOutboundAPI,
    dispatch_id: str,
    room_name: str,
) -> None:
    with suppress(Exception):
        await asyncio.shield(
            client.agent_dispatch.delete_dispatch(dispatch_id, room_name)
        )


def _normalize_reminder(value: OutboundReminder | str) -> OutboundReminder:
    if value in {OUTBOUND_REMINDER_PAPER_PRACTICE, PAPER_PRACTICE_REMINDER}:
        return PAPER_PRACTICE_REMINDER
    raise OutboundConfigurationError("The outbound reminder is not supported.")


def _validate_phone_number(value: object) -> str:
    if not isinstance(value, str) or _E164_PHONE_NUMBER.fullmatch(value) is None:
        raise OutboundConfigurationError("Phone number must use E.164 format.")
    return value


def _validate_sip_trunk_id(value: object) -> str:
    if not isinstance(value, str) or _SIP_TRUNK_ID.fullmatch(value) is None:
        raise OutboundConfigurationError("SIP outbound trunk ID is invalid.")
    return value


def _validate_agent_name(value: object) -> str:
    if not isinstance(value, str) or _AGENT_NAME.fullmatch(value) is None:
        raise OutboundConfigurationError("Agent name is invalid.")
    return value
