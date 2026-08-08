from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fined.market_data.models import MarketQuote, QuoteRequest
from fined.market_data.provider import (
    MARKET_DATA_UNAVAILABLE_MESSAGE,
    MarketDataUnavailableError,
    UnavailableMarketDataProvider,
)


@pytest.mark.parametrize("exchange", ["NFO", "MCX", "nse", " NSE ", ""])
def test_quote_request_rejects_unsupported_or_noncanonical_exchange(
    exchange: str,
) -> None:
    with pytest.raises(ValueError, match="exchange"):
        QuoteRequest(exchange=exchange, symbol_token="3045")


@pytest.mark.parametrize(
    "symbol_token", ["", " 3045", "3045 ", "SBIN", "1.2", "1" * 21]
)
def test_quote_request_rejects_invalid_symbol_token(symbol_token: str) -> None:
    with pytest.raises(ValueError, match="symbol token"):
        QuoteRequest(exchange="NSE", symbol_token=symbol_token)


def test_market_quote_serializes_attributable_decimal_data() -> None:
    exchange_time = datetime(2026, 8, 8, 3, 30, tzinfo=UTC)
    received_time = datetime(2026, 8, 8, 3, 30, 1, tzinfo=UTC)
    quote = MarketQuote(
        exchange="NSE",
        symbol_token="3045",
        trading_symbol="SBIN-EQ",
        last_traded_price=Decimal("812.35"),
        close_price=Decimal("808.10"),
        provider="Angel One SmartAPI",
        exchange_time=exchange_time,
        received_time=received_time,
    )

    assert quote.to_public_dict() == {
        "exchange": "NSE",
        "symbol_token": "3045",
        "trading_symbol": "SBIN-EQ",
        "last_traded_price": "812.35",
        "close_price": "808.10",
        "provider": "Angel One SmartAPI",
        "exchange_time": "2026-08-08T03:30:00+00:00",
        "received_time": "2026-08-08T03:30:01+00:00",
        "is_order": False,
    }


@pytest.mark.asyncio
async def test_unavailable_provider_uses_one_fixed_safe_message() -> None:
    provider = UnavailableMarketDataProvider()

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_quote(QuoteRequest("NSE", "3045"))

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
