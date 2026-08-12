from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from fined.escalation_bridge import (
    HUMAN_HELP_UI_UNAVAILABLE_MESSAGE,
    HumanHelpUIUnavailableError,
    LiveKitHumanHelpBridge,
)


@dataclass
class FakeLocalParticipant:
    response: str = '{"version":1,"opened":true}'
    calls: list[dict[str, object]] = field(default_factory=list)

    async def perform_rpc(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.response


def _public_request() -> dict[str, object]:
    return {
        "version": 1,
        "reference_id": "HELP-A1B2C3D4",
        "reason": "suspected_fraud",
        "summary": "The learner reports an unrecognised account transaction.",
        "checks_completed": "FinEd confirmed the activity was not recognised.",
        "urgency": "high",
        "language": "english",
        "follow_up_method": "in_app",
        "status": "open",
        "created_at": "2026-08-12T06:30:00+00:00",
    }


@pytest.mark.asyncio
async def test_bridge_shows_only_the_public_request_to_the_connected_learner() -> None:
    participant = FakeLocalParticipant()
    bridge = LiveKitHumanHelpBridge(participant, "learner-1")

    acknowledgement = await bridge.show_request(_public_request())

    assert acknowledgement.opened is True
    assert len(participant.calls) == 1
    call = participant.calls[0]
    assert call["destination_identity"] == "learner-1"
    assert call["method"] == "fined.escalation.v1.show_request"
    assert call["response_timeout"] == 5
    assert json.loads(str(call["payload"])) == _public_request()
    assert "caller_id" not in str(call["payload"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        '{"version":1,"opened":false}',
        '{"version":1,"opened":true,"extra":"x"}',
    ],
)
async def test_bridge_fails_closed_on_an_invalid_browser_acknowledgement(
    response: str,
) -> None:
    bridge = LiveKitHumanHelpBridge(
        FakeLocalParticipant(response=response), "learner-1"
    )

    with pytest.raises(HumanHelpUIUnavailableError) as failure:
        await bridge.show_request(_public_request())

    assert str(failure.value) == HUMAN_HELP_UI_UNAVAILABLE_MESSAGE


def test_bridge_requires_a_non_empty_participant_identity() -> None:
    with pytest.raises(ValueError, match="participant identity"):
        LiveKitHumanHelpBridge(FakeLocalParticipant(), " ")
