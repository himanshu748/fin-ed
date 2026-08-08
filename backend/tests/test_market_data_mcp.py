from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fined.market_data.mcp_server import create_mcp_server, get_market_quote_result
from fined.market_data.models import MarketQuote, QuoteRequest
from fined.market_data.provider import MarketDataUnavailableError


class FakeProvider:
    def __init__(self, quote: MarketQuote | None) -> None:
        self.quote = quote
        self.calls: list[QuoteRequest] = []

    async def get_quote(self, request: QuoteRequest) -> MarketQuote:
        self.calls.append(request)
        if self.quote is None:
            raise MarketDataUnavailableError("secret upstream detail")
        return self.quote


def quote() -> MarketQuote:
    return MarketQuote(
        exchange="NSE",
        symbol_token="3045",
        trading_symbol="SBIN-EQ",
        last_traded_price=Decimal("812.35"),
        close_price=Decimal("808.10"),
        provider="Angel One SmartAPI",
        exchange_time=datetime(2026, 8, 8, 3, 30, tzinfo=UTC),
        received_time=datetime(2026, 8, 8, 3, 30, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_mcp_result_uses_shared_validation_and_read_only_shape() -> None:
    provider = FakeProvider(quote())

    result = await get_market_quote_result(provider, "NSE", "3045")

    assert provider.calls == [QuoteRequest("NSE", "3045")]
    assert result["last_traded_price"] == "812.35"
    assert result["is_order"] is False
    assert "read-only" in str(result["message"]).casefold()


@pytest.mark.asyncio
async def test_mcp_result_sanitizes_provider_failure() -> None:
    with pytest.raises(RuntimeError) as failure:
        await get_market_quote_result(FakeProvider(None), "NSE", "3045")

    assert str(failure.value) == "Live market data is temporarily unavailable."
    assert "secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_mcp_server_exposes_only_one_annotated_quote_tool() -> None:
    server = create_mcp_server(FakeProvider(quote()))

    tools = await server.list_tools()

    assert [tool.name for tool in tools] == ["get_market_quote"]
    annotations = tools[0].annotations
    assert annotations is not None
    assert annotations.read_only_hint is True
    assert annotations.destructive_hint is False
    assert annotations.idempotent_hint is True
