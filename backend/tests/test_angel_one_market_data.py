from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from fined.market_data.angel_one import (
    QUOTE_ENDPOINT,
    AngelOneMarketDataConfig,
    AngelOneMarketDataProvider,
    create_market_data_provider,
)
from fined.market_data.models import QuoteRequest
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
