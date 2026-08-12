"""Private, consent-bound automated callbacks for current-session help requests."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from livekit import api

from fined.outbound import (
    HUMAN_HELP_CALLBACK_REMINDER,
    LiveKitOutboundAPI,
    OutboundCallRequest,
    OutboundCallResult,
    OutboundConfigurationError,
    initiate_outbound_call,
)

_REFERENCE_ID = re.compile(r"^HELP-(?:[A-F0-9]{4}-){5}[A-F0-9]{4}$")


class HumanHelpCallbackError(RuntimeError):
    """Fixed public callback failure without carrier or phone-number details."""


@dataclass(frozen=True)
class HumanHelpCallbackAck:
    answered: bool


class HumanHelpCallback:
    async def request_callback(self, reference_id: str) -> HumanHelpCallbackAck:
        raise NotImplementedError


class UnavailableHumanHelpCallback(HumanHelpCallback):
    async def request_callback(self, reference_id: str) -> HumanHelpCallbackAck:
        del reference_id
        raise HumanHelpCallbackError("Automated callbacks are unavailable.")


def _create_livekit_client() -> api.LiveKitAPI:
    return api.LiveKitAPI(failover=False)


class LiveKitHumanHelpCallback(HumanHelpCallback):
    """Place at most one outbound acknowledgement attempt per reference."""

    def __init__(
        self,
        request: OutboundCallRequest,
        *,
        client_factory: Callable[
            [], AbstractAsyncContextManager[LiveKitOutboundAPI]
        ] = _create_livekit_client,
        dial: Callable[
            [LiveKitOutboundAPI, OutboundCallRequest], Awaitable[OutboundCallResult]
        ] = initiate_outbound_call,
    ) -> None:
        self._request = request
        self._client_factory = client_factory
        self._dial = dial
        self._outcomes: dict[str, bool] = {}

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        client_factory: Callable[
            [], AbstractAsyncContextManager[LiveKitOutboundAPI]
        ] = _create_livekit_client,
        dial: Callable[
            [LiveKitOutboundAPI, OutboundCallRequest], Awaitable[OutboundCallResult]
        ] = initiate_outbound_call,
    ) -> LiveKitHumanHelpCallback:
        request = OutboundCallRequest(
            phone_number=environment.get("FINED_ESCALATION_CALLBACK_NUMBER", ""),
            sip_trunk_id=environment.get("SIP_OUTBOUND_TRUNK_ID", ""),
            agent_name=environment.get("FINED_OUTBOUND_AGENT_NAME", "my-agent"),
            reminder=HUMAN_HELP_CALLBACK_REMINDER,
        )
        return cls(request, client_factory=client_factory, dial=dial)

    async def request_callback(self, reference_id: str) -> HumanHelpCallbackAck:
        if (
            not isinstance(reference_id, str)
            or _REFERENCE_ID.fullmatch(reference_id) is None
        ):
            raise OutboundConfigurationError(
                "A valid current help reference is required."
            )
        previous = self._outcomes.get(reference_id)
        if previous is True:
            return HumanHelpCallbackAck(answered=True)
        if previous is False:
            raise HumanHelpCallbackError("The callback attempt was not answered.")
        self._outcomes[reference_id] = False
        try:
            async with self._client_factory() as client:
                await self._dial(client, self._request)
        except Exception:
            raise HumanHelpCallbackError(
                "The callback attempt could not be completed."
            ) from None
        self._outcomes[reference_id] = True
        return HumanHelpCallbackAck(answered=True)
