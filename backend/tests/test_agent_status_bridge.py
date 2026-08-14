from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

import fined.agent_status_bridge as status_bridge_module
from fined.agent_status_bridge import (
    AGENT_STATUS_RPC_METHOD,
    AGENT_STATUS_UI_UNAVAILABLE_MESSAGE,
    AgentStatus,
    AgentStatusUIUnavailableError,
    LiveKitAgentStatusBridge,
    UnavailableAgentStatusBridge,
)


@dataclass
class FakeLocalParticipant:
    response: str = '{"version":1,"accepted":true}'
    calls: list[dict[str, object]] = field(default_factory=list)
    error: Exception | None = None

    async def perform_rpc(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            AgentStatus(
                version=1,
                active_agent="fined",
                display_name="FinEd Saathi",
                voice_name="Nikhil",
                specialty=None,
            ),
            {
                "version": 1,
                "active_agent": "fined",
                "display_name": "FinEd Saathi",
                "voice_name": "Nikhil",
                "specialty": None,
            },
        ),
        (
            AgentStatus(
                version=1,
                active_agent="taxed",
                display_name="TaxEd",
                voice_name="Anusha",
                specialty="Investment Tax Specialist",
            ),
            {
                "version": 1,
                "active_agent": "taxed",
                "display_name": "TaxEd",
                "voice_name": "Anusha",
                "specialty": "Investment Tax Specialist",
            },
        ),
    ],
)
async def test_bridge_publishes_only_exact_status_to_connected_participant(
    status: AgentStatus, expected: dict[str, object]
) -> None:
    # Catches mixed identities or private session data entering the status payload.
    participant = FakeLocalParticipant()
    bridge = LiveKitAgentStatusBridge(participant, "learner-1")

    await bridge.publish(status)

    assert participant.calls == [
        {
            "destination_identity": "learner-1",
            "method": AGENT_STATUS_RPC_METHOD,
            "payload": json.dumps(expected, separators=(",", ":")),
            "response_timeout": 5,
        }
    ]
    payload = str(participant.calls[0]["payload"])
    for private_field in ("phone", "question", "transcript", "caller"):
        assert private_field not in payload.casefold()


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "version": 2,
            "active_agent": "fined",
            "display_name": "FinEd Saathi",
            "voice_name": "Nikhil",
            "specialty": None,
        },
        {
            "version": True,
            "active_agent": "fined",
            "display_name": "FinEd Saathi",
            "voice_name": "Nikhil",
            "specialty": None,
        },
        {
            "version": 1,
            "active_agent": "taxed",
            "display_name": "FinEd Saathi",
            "voice_name": "Nikhil",
            "specialty": None,
        },
        {
            "version": 1,
            "active_agent": "fined",
            "display_name": "FinEd Saathi",
            "voice_name": "Anusha",
            "specialty": "Investment Tax Specialist",
        },
    ],
)
def test_agent_status_rejects_every_noncanonical_combination(
    kwargs: dict[str, object],
) -> None:
    # Catches an internally mixed identity being serialized as trusted UI state.
    with pytest.raises(ValueError, match="agent status"):
        AgentStatus(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "not json",
        '{"version":1,"accepted":false}',
        '{"version":1,"accepted":true,"extra":"secret"}',
        '{"version":1.0,"accepted":true}',
        '{"version":1,"accepted":true,"accepted":true}',
        "x" * 2_000,
    ],
)
async def test_bridge_rejects_nonexact_or_oversized_acknowledgement(
    response: str,
) -> None:
    # Catches loose browser acknowledgement parsing that can hide a failed update.
    bridge = LiveKitAgentStatusBridge(
        FakeLocalParticipant(response=response), "learner-1"
    )

    with pytest.raises(AgentStatusUIUnavailableError) as failure:
        await bridge.publish(AgentStatus.taxed())

    assert str(failure.value) == AGENT_STATUS_UI_UNAVAILABLE_MESSAGE
    assert "secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_bridge_enforces_maximum_utf8_payload_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches payload size validation being omitted before transport.
    participant = FakeLocalParticipant()
    bridge = LiveKitAgentStatusBridge(participant, "learner-1")
    monkeypatch.setattr(status_bridge_module, "MAX_AGENT_STATUS_RPC_BYTES", 1)

    with pytest.raises(AgentStatusUIUnavailableError):
        await bridge.publish(AgentStatus.fined())

    assert participant.calls == []


@pytest.mark.asyncio
async def test_bridge_hides_transport_failure_and_unavailable_bridge_is_noop() -> None:
    # Catches private LiveKit errors escaping or the disabled bridge ending a call.
    participant = FakeLocalParticipant(error=TimeoutError("private RPC timeout"))
    bridge = LiveKitAgentStatusBridge(participant, "learner-1")

    with pytest.raises(AgentStatusUIUnavailableError) as failure:
        await bridge.publish(AgentStatus.fined())

    assert str(failure.value) == AGENT_STATUS_UI_UNAVAILABLE_MESSAGE
    await UnavailableAgentStatusBridge().publish(AgentStatus.taxed())


def test_bridge_requires_a_nonempty_participant_identity() -> None:
    # Catches a status broadcast with no participant-scoped destination.
    with pytest.raises(ValueError, match="participant identity"):
        LiveKitAgentStatusBridge(FakeLocalParticipant(), " ")
