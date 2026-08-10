"""Narrow, participant-scoped LiveKit RPC adapter for paper-trading UI actions."""

from __future__ import annotations

import json
from typing import Protocol

from .models import (
    MAX_RPC_PAYLOAD_BYTES,
    PaperDashboardAck,
    PaperDraftAck,
    PaperOrderDraft,
    PaperOrderResult,
    PaperPortfolioSummary,
    decode_paper_dashboard_ack,
    decode_paper_draft_ack,
    decode_paper_order_result,
    decode_paper_portfolio_summary,
)

PAPER_TRADING_UI_UNAVAILABLE_MESSAGE = "Paper trading is unavailable right now."
RPC_RESPONSE_TIMEOUT_SECONDS = 5

_OPEN_DASHBOARD_METHOD = "fined.paper.v1.open_dashboard"
_PREPARE_ORDER_METHOD = "fined.paper.v1.prepare_order"
_CONFIRM_ORDER_METHOD = "fined.paper.v1.confirm_order"
_GET_PORTFOLIO_SUMMARY_METHOD = "fined.paper.v1.get_portfolio_summary"
_EMPTY_PAPER_REQUEST = '{"version":1,"paper":true}'


class PaperTradingUIUnavailableError(RuntimeError):
    """Fixed public error that cannot expose LiveKit or browser details."""

    def __init__(self) -> None:
        super().__init__(PAPER_TRADING_UI_UNAVAILABLE_MESSAGE)


class PaperTradingBridge(Protocol):
    async def open_dashboard(self) -> PaperDashboardAck: ...

    async def prepare_order(self, draft: PaperOrderDraft) -> PaperDraftAck: ...

    async def confirm_order(self, draft_id: str) -> PaperOrderResult: ...

    async def get_portfolio_summary(self) -> PaperPortfolioSummary: ...


class _LocalParticipant(Protocol):
    async def perform_rpc(
        self,
        *,
        destination_identity: str,
        method: str,
        payload: str,
        response_timeout: float,
    ) -> str: ...


class LiveKitPaperTradingBridge:
    """Send versioned paper requests exclusively to the connected learner."""

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

    async def open_dashboard(self) -> PaperDashboardAck:
        response = await self._perform_rpc(_OPEN_DASHBOARD_METHOD, _EMPTY_PAPER_REQUEST)
        try:
            return decode_paper_dashboard_ack(response)
        except Exception:
            raise PaperTradingUIUnavailableError() from None

    async def prepare_order(self, draft: PaperOrderDraft) -> PaperDraftAck:
        payload = json.dumps(
            draft.to_rpc_payload(), separators=(",", ":"), ensure_ascii=False
        )
        response = await self._perform_rpc(_PREPARE_ORDER_METHOD, payload)
        try:
            ack = decode_paper_draft_ack(response)
            if ack.draft_id != draft.draft_id:
                raise ValueError("browser acknowledged a different draft")
            return ack
        except Exception:
            raise PaperTradingUIUnavailableError() from None

    async def confirm_order(self, draft_id: str) -> PaperOrderResult:
        if not isinstance(draft_id, str) or not draft_id.strip():
            raise PaperTradingUIUnavailableError()
        payload = json.dumps(
            {"version": 1, "paper": True, "draft_id": draft_id},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        response = await self._perform_rpc(_CONFIRM_ORDER_METHOD, payload)
        try:
            result = decode_paper_order_result(response)
            if result.draft_id != draft_id:
                raise ValueError("browser confirmed a different draft")
            return result
        except Exception:
            raise PaperTradingUIUnavailableError() from None

    async def get_portfolio_summary(self) -> PaperPortfolioSummary:
        response = await self._perform_rpc(
            _GET_PORTFOLIO_SUMMARY_METHOD, _EMPTY_PAPER_REQUEST
        )
        try:
            return decode_paper_portfolio_summary(response)
        except Exception:
            raise PaperTradingUIUnavailableError() from None

    async def _perform_rpc(self, method: str, payload: str) -> str:
        if len(payload.encode("utf-8")) > MAX_RPC_PAYLOAD_BYTES:
            raise PaperTradingUIUnavailableError()
        try:
            response = await self._local_participant.perform_rpc(
                destination_identity=self._participant_identity,
                method=method,
                payload=payload,
                response_timeout=RPC_RESPONSE_TIMEOUT_SECONDS,
            )
            if not isinstance(response, str):
                raise ValueError("paper RPC response must be text")
            if len(response.encode("utf-8")) > MAX_RPC_PAYLOAD_BYTES:
                raise ValueError("paper RPC response exceeds the maximum size")
            return response
        except Exception:
            raise PaperTradingUIUnavailableError() from None
