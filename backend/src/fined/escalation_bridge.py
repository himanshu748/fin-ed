"""Participant-scoped LiveKit RPC bridge for the learner's human-help view."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

HUMAN_HELP_UI_UNAVAILABLE_MESSAGE = "Human help is unavailable right now."
HUMAN_HELP_RPC_METHOD = "fined.escalation.v1.show_request"
HUMAN_HELP_RPC_TIMEOUT_SECONDS = 5
MAX_HUMAN_HELP_RPC_BYTES = 8_000


class HumanHelpUIUnavailableError(RuntimeError):
    """Fixed public error that does not expose browser or transport details."""

    def __init__(self) -> None:
        super().__init__(HUMAN_HELP_UI_UNAVAILABLE_MESSAGE)


@dataclass(frozen=True)
class HumanHelpDashboardAck:
    opened: bool


class HumanHelpBridge(Protocol):
    async def show_request(
        self, public_request: Mapping[str, object]
    ) -> HumanHelpDashboardAck: ...


class _LocalParticipant(Protocol):
    async def perform_rpc(
        self,
        *,
        destination_identity: str,
        method: str,
        payload: str,
        response_timeout: float,
    ) -> str: ...


class LiveKitHumanHelpBridge:
    """Show one public escalation only to its connected learner."""

    def __init__(
        self, local_participant: _LocalParticipant, participant_identity: str
    ) -> None:
        if (
            not isinstance(participant_identity, str)
            or not participant_identity.strip()
        ):
            raise ValueError("participant identity must be non-empty text")
        self._local_participant = local_participant
        self._participant_identity = participant_identity

    async def show_request(
        self, public_request: Mapping[str, object]
    ) -> HumanHelpDashboardAck:
        try:
            payload = json.dumps(
                dict(public_request), separators=(",", ":"), ensure_ascii=False
            )
            if len(payload.encode("utf-8")) > MAX_HUMAN_HELP_RPC_BYTES:
                raise ValueError("human-help request is too large")
            response = await self._local_participant.perform_rpc(
                destination_identity=self._participant_identity,
                method=HUMAN_HELP_RPC_METHOD,
                payload=payload,
                response_timeout=HUMAN_HELP_RPC_TIMEOUT_SECONDS,
            )
            decoded = json.loads(response)
            if decoded != {"version": 1, "opened": True}:
                raise ValueError("invalid human-help acknowledgement")
            return HumanHelpDashboardAck(opened=True)
        except Exception:
            raise HumanHelpUIUnavailableError() from None
