from __future__ import annotations

from typing import Protocol

from fined.market_data.models import (
    InstrumentSearchRequest,
    MarketInstrument,
    MarketQuote,
    QuoteRequest,
)

MARKET_DATA_UNAVAILABLE_MESSAGE = "Live market data is temporarily unavailable."


class MarketDataUnavailableError(RuntimeError):
    """Safe public failure for missing, stale, or rejected quote data."""


class MarketDataProvider(Protocol):
    async def get_quote(self, request: QuoteRequest) -> MarketQuote: ...

    async def search_instruments(
        self, request: InstrumentSearchRequest
    ) -> tuple[MarketInstrument, ...]: ...


class UnavailableMarketDataProvider:
    async def get_quote(self, request: QuoteRequest) -> MarketQuote:
        del request
        raise MarketDataUnavailableError(MARKET_DATA_UNAVAILABLE_MESSAGE)

    async def search_instruments(
        self, request: InstrumentSearchRequest
    ) -> tuple[MarketInstrument, ...]:
        del request
        raise MarketDataUnavailableError(MARKET_DATA_UNAVAILABLE_MESSAGE)
