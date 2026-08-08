from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from fined.market_data.angel_one import (
    QUOTE_ENDPOINT,
    SEARCH_SCRIP_ENDPOINT,
    AngelOneMarketDataConfig,
    AngelOneMarketDataProvider,
    create_market_data_provider,
)
from fined.market_data.models import InstrumentSearchRequest, QuoteRequest
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


@pytest.mark.asyncio
async def test_angel_one_provider_posts_ltp_request_and_normalizes_quote() -> None:
    seen: dict[str, object] = {}

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
async def test_search_scrip_posts_only_to_read_only_endpoint() -> None:
    captured_request: httpx.Request | None = None

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

    assert results[0].trading_symbol == "RELIANCE-EQ"
    assert captured_request is not None
    assert captured_request.url.path.endswith("/order/v1/searchScrip")
    assert json.loads(captured_request.content) == {
        "exchange": "NSE",
        "searchscrip": "RELIANCE",
    }
    assert captured_request.url == httpx.URL(SEARCH_SCRIP_ENDPOINT)


@pytest.mark.asyncio
async def test_search_scrip_without_exchange_queries_nse_and_bse_and_merges_results() -> (
    None
):
    captured_requests: list[httpx.Request] = []

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
