"""Strict participant-scoped active-agent status publishing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

AGENT_STATUS_RPC_METHOD = "fined.agent.v1.status"
AGENT_STATUS_QUERY_RPC_METHOD = "fined.agent.v1.status.query"
AGENT_STATUS_RPC_TIMEOUT_SECONDS = 5
MAX_AGENT_STATUS_RPC_BYTES = 1_024
AGENT_STATUS_UI_UNAVAILABLE_MESSAGE = "Agent status is unavailable right now."
AGENT_STATUS_QUERY_UNAVAILABLE_MESSAGE = "Agent status query is unavailable."

AgentName = Literal["fined", "taxed"]

_FINED_PAYLOAD = {
    "version": 1,
    "active_agent": "fined",
    "display_name": "FinEd Saathi",
    "voice_name": "Nikhil",
    "specialty": None,
}
_TAXED_PAYLOAD = {
    "version": 1,
    "active_agent": "taxed",
    "display_name": "TaxEd",
    "voice_name": "Anusha",
    "specialty": "Investment Tax Specialist",
}


class AgentStatusUIUnavailableError(RuntimeError):
    """Fixed public failure without browser or transport details."""

    def __init__(self) -> None:
        super().__init__(AGENT_STATUS_UI_UNAVAILABLE_MESSAGE)


def decode_agent_status_query(payload: str) -> None:
    """Accept only the bounded version-one read-only query shape."""

    try:
        if (
            not isinstance(payload, str)
            or len(payload.encode("utf-8")) > MAX_AGENT_STATUS_RPC_BYTES
        ):
            raise ValueError
        pairs = json.loads(payload, object_pairs_hook=list)
        if (
            not isinstance(pairs, list)
            or len(pairs) != 1
            or not isinstance(pairs[0], tuple)
            or pairs[0][0] != "version"
            or type(pairs[0][1]) is not int
            or pairs[0][1] != 1
        ):
            raise ValueError
    except Exception:
        raise ValueError(AGENT_STATUS_QUERY_UNAVAILABLE_MESSAGE) from None


def encode_active_agent_status(active_agent_name: object) -> str:
    """Encode one canonical current status without accepting browser state."""

    try:
        if active_agent_name == "fined":
            status = AgentStatus.fined()
        elif active_agent_name == "taxed":
            status = AgentStatus.taxed()
        else:
            raise ValueError
        return json.dumps(
            status.to_payload(), separators=(",", ":"), ensure_ascii=False
        )
    except Exception:
        raise ValueError(AGENT_STATUS_QUERY_UNAVAILABLE_MESSAGE) from None


@dataclass(frozen=True)
class AgentStatus:
    version: int
    active_agent: AgentName
    display_name: str
    voice_name: str
    specialty: str | None

    def __post_init__(self) -> None:
        if (
            type(self.version) is not int
            or self.version != 1
            or self.to_payload() not in (_FINED_PAYLOAD, _TAXED_PAYLOAD)
        ):
            raise ValueError("agent status must use one canonical identity")

    @classmethod
    def fined(cls) -> AgentStatus:
        return cls(
            version=1,
            active_agent="fined",
            display_name="FinEd Saathi",
            voice_name="Nikhil",
            specialty=None,
        )

    @classmethod
    def taxed(cls) -> AgentStatus:
        return cls(
            version=1,
            active_agent="taxed",
            display_name="TaxEd",
            voice_name="Anusha",
            specialty="Investment Tax Specialist",
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "active_agent": self.active_agent,
            "display_name": self.display_name,
            "voice_name": self.voice_name,
            "specialty": self.specialty,
        }


class AgentStatusBridge(Protocol):
    async def publish(self, status: AgentStatus) -> None: ...


class _LocalParticipant(Protocol):
    async def perform_rpc(
        self,
        *,
        destination_identity: str,
        method: str,
        payload: str,
        response_timeout: float,
    ) -> str: ...


class LiveKitAgentStatusBridge:
    """Publish active identity only to the connected learner participant."""

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

    async def publish(self, status: AgentStatus) -> None:
        try:
            if not isinstance(status, AgentStatus):
                raise ValueError("agent status must be validated")
            payload = json.dumps(
                status.to_payload(), separators=(",", ":"), ensure_ascii=False
            )
            if len(payload.encode("utf-8")) > MAX_AGENT_STATUS_RPC_BYTES:
                raise ValueError("agent status payload is too large")
            response = await self._local_participant.perform_rpc(
                destination_identity=self._participant_identity,
                method=AGENT_STATUS_RPC_METHOD,
                payload=payload,
                response_timeout=AGENT_STATUS_RPC_TIMEOUT_SECONDS,
            )
            if not isinstance(response, str):
                raise ValueError("agent status acknowledgement must be text")
            if len(response.encode("utf-8")) > MAX_AGENT_STATUS_RPC_BYTES:
                raise ValueError("agent status acknowledgement is too large")
            acknowledgement_pairs = json.loads(response, object_pairs_hook=list)
            if (
                not isinstance(acknowledgement_pairs, list)
                or len(acknowledgement_pairs) != 2
            ):
                raise ValueError("invalid agent status acknowledgement")
            acknowledgement = dict(acknowledgement_pairs)
            if (
                set(acknowledgement) != {"version", "accepted"}
                or type(acknowledgement["version"]) is not int
                or acknowledgement["version"] != 1
                or acknowledgement["accepted"] is not True
            ):
                raise ValueError("invalid agent status acknowledgement")
        except Exception:
            raise AgentStatusUIUnavailableError() from None


class UnavailableAgentStatusBridge:
    """No-op publisher for sessions without an authorized browser RPC."""

    async def publish(self, status: AgentStatus) -> None:
        del status
