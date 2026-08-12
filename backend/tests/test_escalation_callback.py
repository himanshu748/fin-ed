from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from typing import Any

import pytest

from fined.escalation_callback import LiveKitHumanHelpCallback
from fined.outbound import HUMAN_HELP_CALLBACK_REMINDER, OutboundConfigurationError


class FakeClientContext(AbstractAsyncContextManager[object]):
    async def __aenter__(self) -> object:
        return SimpleNamespace()

    async def __aexit__(self, *args: object) -> None:
        del args


def test_callback_configuration_rejects_missing_private_destination() -> None:
    # Catches a browser or model supplied phone number becoming a dial target.
    with pytest.raises(OutboundConfigurationError):
        LiveKitHumanHelpCallback.from_environment(
            {
                "SIP_OUTBOUND_TRUNK_ID": "ST_abc12345",
                "FINED_OUTBOUND_AGENT_NAME": "my-agent",
            }
        )


@pytest.mark.asyncio
async def test_callback_places_one_private_automated_call_per_reference() -> None:
    # Catches repeated tool calls creating duplicate dials or the wrong reminder.
    requests: list[object] = []
    clients_created = 0

    def client_factory() -> FakeClientContext:
        nonlocal clients_created
        clients_created += 1
        return FakeClientContext()

    async def dial(client: object, request: object) -> Any:
        del client
        requests.append(request)
        return SimpleNamespace(sip_call_id="call-123")

    callback = LiveKitHumanHelpCallback.from_environment(
        {
            "FINED_ESCALATION_CALLBACK_NUMBER": "+919876543210",
            "SIP_OUTBOUND_TRUNK_ID": "ST_abc12345",
            "FINED_OUTBOUND_AGENT_NAME": "my-agent",
        },
        client_factory=client_factory,
        dial=dial,
    )

    first = await callback.request_callback("HELP-A1B2-C3D4-E5F6-0123-4567-89AB")
    duplicate = await callback.request_callback("HELP-A1B2-C3D4-E5F6-0123-4567-89AB")

    assert first.answered is True
    assert duplicate.answered is True
    assert clients_created == 1
    assert len(requests) == 1
    request = requests[0]
    assert request.phone_number == "+919876543210"  # type: ignore[attr-defined]
    assert request.sip_trunk_id == "ST_abc12345"  # type: ignore[attr-defined]
    assert request.agent_name == "my-agent"  # type: ignore[attr-defined]
    assert request.reminder == HUMAN_HELP_CALLBACK_REMINDER  # type: ignore[attr-defined]
