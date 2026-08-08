from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fined.market_data.models import (
    InstrumentSearchRequest,
    MarketInstrument,
    MarketQuote,
    QuoteRequest,
)
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


def test_instrument_search_rejects_blank_or_oversized_query() -> None:
    with pytest.raises(ValueError):
        InstrumentSearchRequest(query=" ")
    with pytest.raises(ValueError):
        InstrumentSearchRequest(query="A" * 129)


def test_instrument_search_trims_query_and_bounds_limit() -> None:
    request = InstrumentSearchRequest(query=" RELIANCE ", exchange="NSE", limit=5)

    assert request.query == "RELIANCE"
    assert request.exchange == "NSE"
    with pytest.raises(ValueError, match="limit"):
        InstrumentSearchRequest(query="RELIANCE", limit=0)
    with pytest.raises(ValueError, match="limit"):
        InstrumentSearchRequest(query="RELIANCE", limit=6)


@pytest.mark.parametrize("exchange", ["NFO", "nse", " NSE "])
def test_instrument_search_rejects_non_cash_exchange(exchange: str) -> None:
    with pytest.raises(ValueError, match="exchange"):
        InstrumentSearchRequest(query="RELIANCE", exchange=exchange)


def test_market_instrument_requires_cash_exchange_and_numeric_token() -> None:
    item = MarketInstrument(
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        series="EQ",
    )

    assert item.to_public_dict() == {
        "exchange": "NSE",
        "symbol_token": "2885",
        "trading_symbol": "RELIANCE-EQ",
        "series": "EQ",
        "is_order": False,
    }
    with pytest.raises(ValueError, match="exchange"):
        MarketInstrument(exchange="NFO", symbol_token="2885", trading_symbol="X")
    with pytest.raises(ValueError, match="symbol token"):
        MarketInstrument(exchange="NSE", symbol_token="X", trading_symbol="X")
    with pytest.raises(ValueError, match="trading symbol"):
        MarketInstrument(exchange="NSE", symbol_token="2885", trading_symbol=" ")


@pytest.mark.parametrize("series", ["eq", " EQ", "EQ ", "E-Q", "", 1])
def test_market_instrument_rejects_untrusted_noncanonical_series(
    series: object,
) -> None:
    with pytest.raises(ValueError, match="series"):
        MarketInstrument(
            exchange="NSE",
            symbol_token="2885",
            trading_symbol="RELIANCE-EQ",
            series=series,  # type: ignore[arg-type]
        )


def test_market_instrument_carries_explicit_unknown_provider_series() -> None:
    item = MarketInstrument(
        exchange="BSE",
        symbol_token="500325",
        trading_symbol="RELIANCE",
        series=None,
    )

    assert item.to_public_dict()["series"] is None


@pytest.mark.asyncio
async def test_unavailable_provider_uses_one_fixed_safe_message() -> None:
    provider = UnavailableMarketDataProvider()

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_quote(QuoteRequest("NSE", "3045"))

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
