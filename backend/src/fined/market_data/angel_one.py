from __future__ import annotations

import ipaddress
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from fined.market_data.models import (
    InstrumentSearchRequest,
    MarketInstrument,
    MarketQuote,
    QuoteRequest,
)
from fined.market_data.provider import (
    MARKET_DATA_UNAVAILABLE_MESSAGE,
    MarketDataProvider,
    MarketDataUnavailableError,
    UnavailableMarketDataProvider,
)

QUOTE_ENDPOINT = (
    "https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/"
)
SEARCH_SCRIP_ENDPOINT = (
    "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/searchScrip"
)
PROVIDER_NAME = "Angel One SmartAPI"
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_MAX_AGE_SECONDS = 120
_MAC_ADDRESS = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_INDIA_TIME = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class AngelOneMarketDataConfig:
    api_key: str
    access_token: str
    client_local_ip: str
    client_public_ip: str
    mac_address: str

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.access_token.strip():
            raise ValueError("Angel One credentials are incomplete")
        ipaddress.ip_address(self.client_local_ip)
        ipaddress.ip_address(self.client_public_ip)
        if not _MAC_ADDRESS.fullmatch(self.mac_address):
            raise ValueError("Angel One MAC address is invalid")


class AngelOneMarketDataProvider:
    def __init__(
        self,
        config: AngelOneMarketDataConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] | None = None,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("quote maximum age must be positive")
        self._config = config
        self._transport = transport
        self._now = now or (lambda: datetime.now(UTC))
        self._max_age_seconds = max_age_seconds

    async def get_quote(self, request: QuoteRequest) -> MarketQuote:
        payload = {
            "mode": "LTP",
            "exchangeTokens": {request.exchange: [request.symbol_token]},
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(3.0),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    QUOTE_ENDPOINT,
                    content=json.dumps(payload, separators=(",", ":")),
                    headers=self._authenticated_headers(),
                )
            if (
                response.status_code != 200
                or len(response.content) > MAX_RESPONSE_BYTES
            ):
                raise ValueError("invalid quote response")
            data = response.json()
            quote = self._parse_quote(data, request)
        except Exception:
            raise MarketDataUnavailableError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
        return quote

    async def search_instruments(
        self, request: InstrumentSearchRequest
    ) -> tuple[MarketInstrument, ...]:
        search_requests = (
            (request,)
            if request.exchange is not None
            else tuple(
                InstrumentSearchRequest(
                    query=request.query, exchange=exchange, limit=request.limit
                )
                for exchange in ("NSE", "BSE")
            )
        )
        instruments: list[MarketInstrument] = []
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(3.0),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                for search_request in search_requests:
                    payload = {
                        "exchange": search_request.exchange,
                        "searchscrip": search_request.query,
                    }
                    # Angel One names this read-only instrument lookup under order/v1.
                    response = await client.post(
                        SEARCH_SCRIP_ENDPOINT,
                        content=json.dumps(payload, separators=(",", ":")),
                        headers=self._authenticated_headers(),
                    )
                    if (
                        response.status_code != 200
                        or len(response.content) > MAX_RESPONSE_BYTES
                    ):
                        raise ValueError("invalid instrument search response")
                    instruments.extend(
                        self._parse_instruments(response.json(), search_request)
                    )
        except Exception:
            raise MarketDataUnavailableError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
        return self._rank_instruments(instruments, request)

    def _authenticated_headers(self) -> dict[str, str]:
        return {
            "X-PrivateKey": self._config.api_key,
            "Authorization": f"Bearer {self._config.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": self._config.client_local_ip,
            "X-ClientPublicIP": self._config.client_public_ip,
            "X-MACAddress": self._config.mac_address,
        }

    def _parse_quote(self, value: object, request: QuoteRequest) -> MarketQuote:
        if not isinstance(value, dict) or value.get("status") is not True:
            raise ValueError("quote request was not successful")
        data = value.get("data")
        if not isinstance(data, dict):
            raise ValueError("quote data is missing")
        fetched = data.get("fetched")
        if not isinstance(fetched, list) or len(fetched) != 1:
            raise ValueError("quote result cardinality is invalid")
        row = fetched[0]
        if not isinstance(row, dict):
            raise ValueError("quote row is invalid")
        if (
            row.get("exchange") != request.exchange
            or str(row.get("symbolToken", "")) != request.symbol_token
        ):
            raise ValueError("quote instrument does not match request")
        trading_symbol = _required_text(row, "tradingSymbol")
        ltp = _positive_decimal(row.get("ltp"))
        close = _positive_decimal(row.get("close"))
        exchange_time = _exchange_time(_required_text(row, "exchangeFeedTime"))
        received_time = self._now().astimezone(UTC)
        age = (received_time - exchange_time).total_seconds()
        if age < -5 or age > self._max_age_seconds:
            raise ValueError("quote is stale")
        return MarketQuote(
            exchange=request.exchange,
            symbol_token=request.symbol_token,
            trading_symbol=trading_symbol,
            last_traded_price=ltp,
            close_price=close,
            provider=PROVIDER_NAME,
            exchange_time=exchange_time,
            received_time=received_time,
        )

    def _parse_instruments(
        self, value: object, request: InstrumentSearchRequest
    ) -> tuple[MarketInstrument, ...]:
        if not isinstance(value, dict) or value.get("status") is not True:
            raise ValueError("instrument search was not successful")
        data = value.get("data")
        if not isinstance(data, list):
            raise ValueError("instrument search data is missing")

        instruments: list[MarketInstrument] = []
        seen: set[tuple[str, str]] = set()
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("instrument search row is invalid")
            exchange = _required_text(row, "exchange")
            if exchange not in {"NSE", "BSE"} or (
                request.exchange is not None and exchange != request.exchange
            ):
                raise ValueError("instrument exchange is invalid")
            instrument = MarketInstrument(
                exchange=exchange,
                trading_symbol=_required_text(row, "tradingsymbol"),
                symbol_token=_required_text(row, "symboltoken"),
            )
            key = (instrument.exchange, instrument.symbol_token)
            if key not in seen:
                seen.add(key)
                instruments.append(instrument)

        return self._rank_instruments(instruments, request)

    def _rank_instruments(
        self,
        instruments: list[MarketInstrument],
        request: InstrumentSearchRequest,
    ) -> tuple[MarketInstrument, ...]:
        deduplicated: dict[tuple[str, str], MarketInstrument] = {}
        for instrument in instruments:
            deduplicated.setdefault(
                (instrument.exchange, instrument.symbol_token), instrument
            )
        ranked = sorted(
            deduplicated.values(),
            key=lambda item: (
                not item.trading_symbol.startswith(request.query),
                item.trading_symbol,
                item.exchange,
                item.symbol_token,
            ),
        )
        return tuple(ranked[: request.limit])


def create_market_data_provider(
    *,
    environment: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MarketDataProvider:
    source = os.environ if environment is None else environment
    required = (
        "ANGEL_ONE_API_KEY",
        "ANGEL_ONE_ACCESS_TOKEN",
        "ANGEL_ONE_CLIENT_LOCAL_IP",
        "ANGEL_ONE_CLIENT_PUBLIC_IP",
        "ANGEL_ONE_MAC_ADDRESS",
    )
    if any(not source.get(name, "").strip() for name in required):
        return UnavailableMarketDataProvider()
    try:
        config = AngelOneMarketDataConfig(
            api_key=source["ANGEL_ONE_API_KEY"],
            access_token=source["ANGEL_ONE_ACCESS_TOKEN"],
            client_local_ip=source["ANGEL_ONE_CLIENT_LOCAL_IP"],
            client_public_ip=source["ANGEL_ONE_CLIENT_PUBLIC_IP"],
            mac_address=source["ANGEL_ONE_MAC_ADDRESS"],
        )
    except (KeyError, ValueError):
        return UnavailableMarketDataProvider()
    return AngelOneMarketDataProvider(config, transport=transport)


def _required_text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be non-empty text")
    return item


def _positive_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("quote price is invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("quote price is invalid") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("quote price is invalid")
    return parsed


def _exchange_time(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%d-%b-%Y %H:%M:%S")
    except ValueError:
        raise ValueError("exchange feed time is invalid") from None
    return parsed.replace(tzinfo=_INDIA_TIME).astimezone(UTC)
