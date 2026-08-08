from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

_SYMBOL_TOKEN = re.compile(r"^[0-9]{1,20}$")
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

    def __post_init__(self) -> None:
        QuoteRequest(self.exchange, self.symbol_token)
        if not isinstance(self.trading_symbol, str) or not self.trading_symbol.strip():
            raise ValueError("trading symbol must be non-empty text")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "symbol_token": self.symbol_token,
            "trading_symbol": self.trading_symbol,
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
