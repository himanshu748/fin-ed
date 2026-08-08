from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from fined.paper_trading.bridge import (
    PAPER_TRADING_UI_UNAVAILABLE_MESSAGE,
    LiveKitPaperTradingBridge,
    PaperTradingUIUnavailableError,
)
from fined.paper_trading.models import MAX_RPC_PAYLOAD_BYTES, PaperOrderDraft


@dataclass
class RpcCall:
    destination_identity: str
    method: str
    payload: str
    response_timeout: float


class FakeLocalParticipant:
    def __init__(self, response: str = '{"version":1,"paper":true,"opened":true}'):
        self.calls: list[RpcCall] = []
        self.response = response
        self.error: Exception | None = None

    async def perform_rpc(
        self,
        *,
        destination_identity: str,
        method: str,
        payload: str,
        response_timeout: float,
    ) -> str:
        self.calls.append(
            RpcCall(destination_identity, method, payload, response_timeout)
        )
        if self.error is not None:
            raise self.error
        return self.response


def draft() -> PaperOrderDraft:
    return PaperOrderDraft(
        draft_id="draft-1",
        side="buy",
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        quantity=2,
        price_paise=250_050,
        quote_provider="Angel One SmartAPI",
        quote_time=datetime(2026, 8, 8, 9, 15, tzinfo=UTC),
        expires_at=datetime(2026, 8, 8, 9, 15, 30, tzinfo=UTC),
        notional_paise=500_100,
        charge_paise=123,
        cash_effect_paise=-500_223,
        charge_status="estimated",
    )


@pytest.mark.asyncio
async def test_open_targets_only_the_connected_learner() -> None:
    fake = FakeLocalParticipant()
    bridge = LiveKitPaperTradingBridge(fake, "learner-1")

    result = await bridge.open_dashboard()

    assert fake.calls[0].destination_identity == "learner-1"
    assert fake.calls[0].method == "fined.paper.v1.open_dashboard"
    assert fake.calls[0].payload == '{"version":1,"paper":true}'
    assert fake.calls[0].response_timeout == 5
    assert result.opened is True


@pytest.mark.asyncio
async def test_prepare_order_sends_only_the_public_draft_payload() -> None:
    fake = FakeLocalParticipant(
        '{"version":1,"paper":true,"prepared":true,"draft_id":"draft-1"}'
    )
    bridge = LiveKitPaperTradingBridge(fake, "learner-1")

    result = await bridge.prepare_order(draft())

    assert fake.calls[0].method == "fined.paper.v1.prepare_order"
    assert json.loads(fake.calls[0].payload)["draft_id"] == "draft-1"
    assert result.draft_id == "draft-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "not json",
        '{"version":true,"paper":true,"opened":true}',
        '{"version":1.0,"paper":true,"opened":true}',
        '{"version":"1","paper":true,"opened":true}',
        '{"version":2,"paper":true,"opened":true}',
        '{"version":1,"paper":true,"opened":true,"access_token":"secret"}',
        "x" * (MAX_RPC_PAYLOAD_BYTES + 1),
        '{"version":1,"paper":true,"cash_paise":-1,"holdings_value_paise":0,"total_value_paise":0}',
    ],
)
async def test_bridge_sanitizes_invalid_or_oversized_responses(response: str) -> None:
    fake = FakeLocalParticipant(response)
    bridge = LiveKitPaperTradingBridge(fake, "learner-1")

    with pytest.raises(PaperTradingUIUnavailableError) as failure:
        await bridge.open_dashboard()

    assert str(failure.value) == PAPER_TRADING_UI_UNAVAILABLE_MESSAGE
    assert "secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_bridge_sanitizes_livekit_timeouts() -> None:
    fake = FakeLocalParticipant()
    fake.error = TimeoutError("private LiveKit failure")
    bridge = LiveKitPaperTradingBridge(fake, "learner-1")

    with pytest.raises(PaperTradingUIUnavailableError) as failure:
        await bridge.open_dashboard()

    assert str(failure.value) == PAPER_TRADING_UI_UNAVAILABLE_MESSAGE
    assert "private" not in str(failure.value)


@pytest.mark.asyncio
async def test_summary_sanitizes_negative_portfolio_values() -> None:
    fake = FakeLocalParticipant(
        '{"version":1,"paper":true,"cash_paise":-1,"holdings_value_paise":0,"total_value_paise":0}'
    )
    bridge = LiveKitPaperTradingBridge(fake, "learner-1")

    with pytest.raises(PaperTradingUIUnavailableError):
        await bridge.get_portfolio_summary()
