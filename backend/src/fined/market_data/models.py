from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

_SYMBOL_TOKEN = re.compile(r"^[0-9]{1,20}$")
_SERIES = re.compile(r"^[A-Z0-9]{1,8}$")
SUPPORTED_EXCHANGES = frozenset({"NSE", "BSE"})


@dataclass(frozen=True)
class QuoteRequest:
    exchange: str
    symbol_token: str

    def __post_init__(self) -> None:
        if self.exchange not in SUPPORTED_EXCHANGES:
            raise ValueError("exchange must be NSE or BSE")
        if not isinstance(self.symbol_token, str) or not _SYMBOL_TOKEN.fullmatch(
            self.symbol_token
        ):
            raise ValueError("symbol token must contain 1 to 20 ASCII digits")


@dataclass(frozen=True)
class HistoricalPriceRequest:
    exchange: str
    symbol_token: str
    purchase_date: date
    valuation_date: date

    def __post_init__(self) -> None:
        QuoteRequest(self.exchange, self.symbol_token)
        if type(self.purchase_date) is not date or type(self.valuation_date) is not date:
            raise ValueError("historical dates must be calendar dates")
        if self.purchase_date > self.valuation_date:
            raise ValueError("purchase date must not be after valuation date")


@dataclass(frozen=True)
class HistoricalClose:
    trading_date: date
    close_price: Decimal

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise ValueError("trading date must be a calendar date")
        if not isinstance(self.close_price, Decimal):
            raise ValueError("historical close must be a decimal")
        if not self.close_price.is_finite() or self.close_price <= 0:
            raise ValueError("historical close must be positive and finite")


@dataclass(frozen=True)
class HistoricalPricePair:
    entry: HistoricalClose
    valuation: HistoricalClose
    provider: str

    def __post_init__(self) -> None:
        if self.entry.trading_date > self.valuation.trading_date:
            raise ValueError("historical closes must be in chronological order")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("historical price provider must be non-empty text")


@dataclass(frozen=True)
class InstrumentSearchRequest:
    query: str
    exchange: str | None = None
    limit: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise ValueError("query must be text")
        query = self.query.strip()
        if not query or len(query) > 128:
            raise ValueError("query must contain 1 to 128 characters")
        object.__setattr__(self, "query", query)
        if self.exchange is not None and self.exchange not in SUPPORTED_EXCHANGES:
            raise ValueError("exchange must be NSE or BSE")
        if (
            not isinstance(self.limit, int)
            or isinstance(self.limit, bool)
            or not 1 <= self.limit <= 5
        ):
            raise ValueError("limit must be between 1 and 5")


@dataclass(frozen=True)
class MarketInstrument:
    exchange: str
    symbol_token: str
    trading_symbol: str
    series: str | None = None

    def __post_init__(self) -> None:
        QuoteRequest(self.exchange, self.symbol_token)
        if not isinstance(self.trading_symbol, str) or not self.trading_symbol.strip():
            raise ValueError("trading symbol must be non-empty text")
        if self.series is not None and (
            not isinstance(self.series, str) or not _SERIES.fullmatch(self.series)
        ):
            raise ValueError("series must be canonical uppercase provider text or null")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "symbol_token": self.symbol_token,
            "trading_symbol": self.trading_symbol,
            "series": self.series,
            "is_order": False,
        }


@dataclass(frozen=True)
class MarketQuote:
    exchange: str
    symbol_token: str
    trading_symbol: str
    last_traded_price: Decimal
    close_price: Decimal
    provider: str
    exchange_time: datetime
    received_time: datetime

    def __post_init__(self) -> None:
        QuoteRequest(self.exchange, self.symbol_token)
        if not self.trading_symbol.strip() or not self.provider.strip():
            raise ValueError("quote attribution is incomplete")
        if self.last_traded_price <= 0 or self.close_price <= 0:
            raise ValueError("quote prices must be positive")
        if self.exchange_time.tzinfo is None or self.received_time.tzinfo is None:
            raise ValueError("quote timestamps must be timezone-aware")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "symbol_token": self.symbol_token,
            "trading_symbol": self.trading_symbol,
            "last_traded_price": str(self.last_traded_price),
            "close_price": str(self.close_price),
            "provider": self.provider,
            "exchange_time": self.exchange_time.isoformat(),
            "received_time": self.received_time.isoformat(),
            "is_order": False,
        }
