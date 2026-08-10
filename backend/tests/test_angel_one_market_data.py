from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

import fined.market_data.angel_one as angel_one
from fined.market_data.angel_one import (
    HISTORICAL_CANDLE_ENDPOINT,
    QUOTE_ENDPOINT,
    SEARCH_SCRIP_ENDPOINT,
    AngelOneMarketDataConfig,
    AngelOneMarketDataProvider,
    create_market_data_provider,
)
from fined.market_data.models import (
    HistoricalPriceRequest,
    InstrumentSearchRequest,
    QuoteRequest,
)
from fined.market_data.provider import (
    MARKET_DATA_UNAVAILABLE_MESSAGE,
    MarketDataUnavailableError,
    UnavailableMarketDataProvider,
)


def config() -> AngelOneMarketDataConfig:
    return AngelOneMarketDataConfig(
        api_key="test-api-key",
        access_token="token",
        client_local_ip="127.0.0.1",
        client_public_ip="203.0.113.10",
        mac_address="00:11:22:33:44:55",
    )


def capture_async_client_constructions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    original = angel_one.httpx.AsyncClient
    constructions: list[int] = []

    def counting_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        constructions.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(angel_one.httpx, "AsyncClient", counting_async_client)
    return constructions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reassigned_endpoint",
    [
        (
            "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/"
            + "place"
            + "Order"
        ),
        "https://example.invalid/account/profile",
    ],
)
async def test_quote_rejects_runtime_reassigned_endpoint_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    reassigned_endpoint: str,
) -> None:
    transport_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(500, request=request)

    monkeypatch.setattr(angel_one, "QUOTE_ENDPOINT", reassigned_endpoint)
    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_quote(QuoteRequest("NSE", "3045"))

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert transport_calls == 0


@pytest.mark.asyncio
async def test_search_rejects_f_string_forbidden_endpoint_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(500, request=request)

    endpoint_action = "getProfile"
    reassigned_endpoint = (
        f"https://apiconnect.angelone.in/rest/secure/angelbroking/user/v1/"
        f"{endpoint_action}"
    )
    monkeypatch.setattr(angel_one, "SEARCH_SCRIP_ENDPOINT", reassigned_endpoint)
    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.search_instruments(
            InstrumentSearchRequest(query="RELIANCE", exchange="NSE")
        )

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert transport_calls == 0


@pytest.mark.asyncio
async def test_historical_prices_reject_runtime_reassigned_endpoint_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches endpoint mutation turning a read-only history lookup into account access.
    transport_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(500, request=request)

    monkeypatch.setattr(
        angel_one,
        "HISTORICAL_CANDLE_ENDPOINT",
        "https://apiconnect.angelone.in/rest/secure/angelbroking/portfolio/v1/getHolding",
    )
    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_historical_prices(
            HistoricalPriceRequest("NSE", "2885", date(2024, 1, 6), date(2026, 8, 9))
        )

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert transport_calls == 0


@pytest.mark.asyncio
async def test_batch_transport_gate_allows_exact_endpoints_in_request_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[httpx.Request] = []
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={"status": True, "sequence": len(captured_requests)},
            request=request,
        )

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    responses = await provider._post_read_only_batch(
        (
            (QUOTE_ENDPOINT, {"probe": "quote"}),
            (SEARCH_SCRIP_ENDPOINT, {"probe": "search"}),
            (HISTORICAL_CANDLE_ENDPOINT, {"probe": "history"}),
        )
    )

    assert [response.json()["sequence"] for response in responses] == [1, 2, 3]
    assert client_constructions == [1]
    assert [request.url for request in captured_requests] == [
        httpx.URL(QUOTE_ENDPOINT),
        httpx.URL(SEARCH_SCRIP_ENDPOINT),
        httpx.URL(HISTORICAL_CANDLE_ENDPOINT),
    ]
    assert [json.loads(request.content) for request in captured_requests] == [
        {"probe": "quote"},
        {"probe": "search"},
        {"probe": "history"},
    ]


@pytest.mark.asyncio
async def test_batch_gate_rejects_every_request_before_constructing_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[httpx.Request] = []
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, request=request)

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )
    forbidden = (
        "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/"
        + "cancel"
        + "Order"
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider._post_read_only_batch(
            (
                (QUOTE_ENDPOINT, {"probe": "allowed-first"}),
                (forbidden, {"probe": "forbidden-second"}),
                (SEARCH_SCRIP_ENDPOINT, {"probe": "allowed-third"}),
            )
        )

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert client_constructions == []
    assert captured_requests == []


@pytest.mark.asyncio
async def test_angel_one_provider_posts_ltp_request_and_normalizes_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "SUCCESS",
                "errorcode": "",
                "data": {
                    "fetched": [
                        {
                            "exchange": "NSE",
                            "tradingSymbol": "SBIN-EQ",
                            "symbolToken": "3045",
                            "ltp": 812.35,
                            "close": 808.1,
                            "exchangeFeedTime": "08-Aug-2026 09:00:00",
                        }
                    ],
                    "unfetched": [],
                },
            },
        )

    provider = AngelOneMarketDataProvider(
        config(),
        transport=httpx.MockTransport(handler),
        now=lambda: datetime(2026, 8, 8, 3, 30, 1, tzinfo=UTC),
    )

    quote = await provider.get_quote(QuoteRequest("NSE", "3045"))

    assert client_constructions == [1]
    assert seen["url"] == QUOTE_ENDPOINT
    headers = seen["headers"]
    assert isinstance(headers, dict)
    assert headers["x-privatekey"] == "test-api-key"
    assert headers["authorization"] == "Bearer token"
    assert seen["body"] == '{"mode":"LTP","exchangeTokens":{"NSE":["3045"]}}'
    assert quote.trading_symbol == "SBIN-EQ"
    assert str(quote.last_traded_price) == "812.35"
    assert str(quote.close_price) == "808.1"
    assert quote.exchange_time == datetime(2026, 8, 8, 3, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_historical_prices_use_two_bounded_daily_windows_and_available_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches downloading an entire holding period or choosing weekend boundary dates.
    captured_requests: list[httpx.Request] = []
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = json.loads(request.content)
        if body["fromdate"] == "2024-01-06 09:15":
            data = [
                ["2024-01-08T00:00:00+05:30", 99, 102, 98, 100, 1500],
                ["2024-01-09T00:00:00+05:30", 100, 104, 99, 103, 1600],
            ]
        else:
            data = [
                ["2026-08-06T00:00:00+05:30", 123, 126, 122, 124, 1700],
                ["2026-08-07T00:00:00+05:30", 124, 127, 123, 125, 1800],
            ]
        return httpx.Response(
            200,
            json={"status": True, "message": "SUCCESS", "data": data},
            request=request,
        )

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )
    request = HistoricalPriceRequest("NSE", "2885", date(2024, 1, 6), date(2026, 8, 9))

    prices = await provider.get_historical_prices(request)

    assert client_constructions == [1]
    assert [item.url for item in captured_requests] == [
        httpx.URL(HISTORICAL_CANDLE_ENDPOINT),
        httpx.URL(HISTORICAL_CANDLE_ENDPOINT),
    ]
    assert [json.loads(item.content) for item in captured_requests] == [
        {
            "exchange": "NSE",
            "symboltoken": "2885",
            "interval": "ONE_DAY",
            "fromdate": "2024-01-06 09:15",
            "todate": "2024-01-20 15:30",
        },
        {
            "exchange": "NSE",
            "symboltoken": "2885",
            "interval": "ONE_DAY",
            "fromdate": "2026-07-26 09:15",
            "todate": "2026-08-09 15:30",
        },
    ]
    assert prices.entry.trading_date == date(2024, 1, 8)
    assert prices.entry.close_price == Decimal("100")
    assert prices.valuation.trading_date == date(2026, 8, 7)
    assert prices.valuation.close_price == Decimal("125")
    assert prices.provider == "Angel One SmartAPI"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        [],
        [["2024-01-08T00:00:00+05:30", 99, 102, 98, 0, 1500]],
        [["not-a-time", 99, 102, 98, 100, 1500]],
        [["2024-02-01T00:00:00+05:30", 99, 102, 98, 100, 1500]],
        [
            ["2024-01-09T00:00:00+05:30", 100, 104, 99, 103, 1600],
            ["2024-01-08T00:00:00+05:30", 99, 102, 98, 100, 1500],
        ],
    ],
)
async def test_historical_prices_sanitize_empty_or_malformed_candles(
    data: list[object],
) -> None:
    # Catches unsafe partial calculations from malformed or out-of-window data.
    provider = AngelOneMarketDataProvider(
        config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"status": True, "message": "SUCCESS", "data": data},
                request=request,
            )
        ),
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_historical_prices(
            HistoricalPriceRequest("NSE", "2885", date(2024, 1, 6), date(2024, 1, 20))
        )

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"ANGEL_ONE_API_KEY": "key"},
        {
            "ANGEL_ONE_API_KEY": "key",
            "ANGEL_ONE_ACCESS_TOKEN": "token",
            "ANGEL_ONE_CLIENT_LOCAL_IP": "127.0.0.1",
            "ANGEL_ONE_CLIENT_PUBLIC_IP": "203.0.113.10",
        },
    ],
)
def test_provider_factory_fails_closed_when_credentials_are_incomplete(
    environment: dict[str, str],
) -> None:
    assert isinstance(
        create_market_data_provider(environment=environment),
        UnavailableMarketDataProvider,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"message": "secret upstream detail"}),
        httpx.Response(200, json={"status": False, "message": "token expired"}),
        httpx.Response(200, json={"status": True, "data": {"fetched": []}}),
        httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "fetched": [
                        {
                            "exchange": "NSE",
                            "symbolToken": "3045",
                            "tradingSymbol": "SBIN-EQ",
                            "ltp": 812.35,
                            "close": 808.1,
                            "exchangeFeedTime": "01-Jan-2020 09:00:00",
                        }
                    ]
                },
            },
        ),
    ],
)
async def test_provider_maps_upstream_and_stale_failures_to_fixed_message(
    response: httpx.Response,
) -> None:
    provider = AngelOneMarketDataProvider(
        config(),
        transport=httpx.MockTransport(lambda request: response),
        now=lambda: datetime(2026, 8, 8, 3, 30, 1, tzinfo=UTC),
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.get_quote(QuoteRequest("NSE", "3045"))

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert "secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_search_scrip_posts_only_to_read_only_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: httpx.Request | None = None
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "RELIANCE-EQ",
                        "symboltoken": "2885",
                    }
                ],
            },
        )

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    results = await provider.search_instruments(
        InstrumentSearchRequest(query="RELIANCE", exchange="NSE")
    )

    assert client_constructions == [1]
    assert results[0].trading_symbol == "RELIANCE-EQ"
    assert results[0].series == "EQ"
    assert captured_request is not None
    assert captured_request.url.path.endswith("/order/v1/searchScrip")
    assert json.loads(captured_request.content) == {
        "exchange": "NSE",
        "searchscrip": "RELIANCE",
    }
    assert captured_request.url == httpx.URL(SEARCH_SCRIP_ENDPOINT)


@pytest.mark.asyncio
async def test_search_scrip_retries_one_transient_provider_rejection() -> None:
    # Catches a single transient Angel rejection ending an otherwise valid voice turn.
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                json={
                    "status": False,
                    "message": "temporary provider failure",
                    "errorcode": "TRANSIENT",
                    "data": None,
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "SUCCESS",
                "errorcode": "",
                "data": [
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "RELIANCE-EQ",
                        "symboltoken": "2885",
                    }
                ],
            },
            request=request,
        )

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    results = await provider.search_instruments(
        InstrumentSearchRequest(query="RELIANCE", exchange="NSE")
    )

    assert attempts == 2
    assert [item.trading_symbol for item in results] == ["RELIANCE-EQ"]


@pytest.mark.asyncio
async def test_search_scrip_without_exchange_queries_nse_and_bse_and_merges_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[httpx.Request] = []
    client_constructions = capture_async_client_constructions(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        exchange = json.loads(request.content)["exchange"]
        data = {
            "NSE": [
                {
                    "exchange": "NSE",
                    "tradingsymbol": "RELIANCE-Z",
                    "symboltoken": "2889",
                },
                {
                    "exchange": "NSE",
                    "tradingsymbol": "A RELIANCE",
                    "symboltoken": "2888",
                },
            ],
            "BSE": [
                {
                    "exchange": "BSE",
                    "tradingsymbol": "RELIANCE-A",
                    "symboltoken": "500325",
                },
                {
                    "exchange": "BSE",
                    "tradingsymbol": "RELIANCE-B",
                    "symboltoken": "500326",
                },
            ],
        }[exchange]
        return httpx.Response(200, json={"status": True, "data": data})

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    results = await provider.search_instruments(
        InstrumentSearchRequest(query="RELIANCE", limit=3)
    )

    assert client_constructions == [1]
    assert [
        (request.url, json.loads(request.content)) for request in captured_requests
    ] == [
        (
            httpx.URL(SEARCH_SCRIP_ENDPOINT),
            {"exchange": "NSE", "searchscrip": "RELIANCE"},
        ),
        (
            httpx.URL(SEARCH_SCRIP_ENDPOINT),
            {"exchange": "BSE", "searchscrip": "RELIANCE"},
        ),
    ]
    assert [(item.exchange, item.symbol_token) for item in results] == [
        ("BSE", "500325"),
        ("BSE", "500326"),
        ("NSE", "2889"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exchange", "trading_symbol", "expected_series"),
    [
        ("NSE", "RELIANCE-EQ", "EQ"),
        ("NSE", "RELIANCE-BE", "BE"),
        ("BSE", "RELIANCE-A", "A"),
        ("BSE", "RELIANCE", None),
    ],
)
async def test_search_scrip_carries_provider_owned_terminal_series(
    exchange: str, trading_symbol: str, expected_series: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "exchange": exchange,
                        "tradingsymbol": trading_symbol,
                        "symboltoken": "2885",
                    }
                ],
            },
        )

    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(handler)
    )

    results = await provider.search_instruments(
        InstrumentSearchRequest(query="RELIANCE", exchange=exchange)
    )

    assert results[0].series == expected_series


@pytest.mark.asyncio
async def test_search_scrip_deduplicates_sorts_prefixes_and_honors_limit() -> None:
    data = [
        {
            "exchange": "BSE",
            "tradingsymbol": "A RELIANCE",
            "symboltoken": "500325",
        },
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE-EQ",
            "symboltoken": "2885",
        },
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE-BE",
            "symboltoken": "2886",
        },
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE-EQ duplicate",
            "symboltoken": "2885",
        },
        {
            "exchange": "BSE",
            "tradingsymbol": "RELIANCE-B",
            "symboltoken": "500326",
        },
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE-C",
            "symboltoken": "2887",
        },
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE-D",
            "symboltoken": "2888",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        exchange = json.loads(request.content)["exchange"]
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": [item for item in data if item["exchange"] == exchange],
            },
        )

    provider = AngelOneMarketDataProvider(
        config(),
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search_instruments(
        InstrumentSearchRequest(query="RELIANCE")
    )

    assert [(item.exchange, item.symbol_token) for item in results] == [
        ("BSE", "500326"),
        ("NSE", "2886"),
        ("NSE", "2887"),
        ("NSE", "2888"),
        ("NSE", "2885"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, content=b"secret upstream failure"),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, content=b"x" * (256 * 1024 + 1)),
        httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "exchange": "NFO",
                        "tradingsymbol": "RELIANCE26AUGFUT",
                        "symboltoken": "999",
                    }
                ],
            },
        ),
        httpx.Response(
            200,
            json={
                "status": True,
                "data": [
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "RELIANCE-EQ",
                        "symboltoken": "not-a-token",
                    }
                ],
            },
        ),
    ],
)
async def test_search_scrip_sanitizes_rejected_or_invalid_responses(
    response: httpx.Response,
) -> None:
    provider = AngelOneMarketDataProvider(
        config(), transport=httpx.MockTransport(lambda request: response)
    )

    with pytest.raises(MarketDataUnavailableError) as failure:
        await provider.search_instruments(InstrumentSearchRequest(query="RELIANCE"))

    assert str(failure.value) == MARKET_DATA_UNAVAILABLE_MESSAGE
    assert "secret" not in str(failure.value)
