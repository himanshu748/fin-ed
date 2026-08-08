from __future__ import annotations

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from fined.market_data.angel_one import create_market_data_provider
from fined.market_data.models import InstrumentSearchRequest, QuoteRequest
from fined.market_data.provider import (
    MARKET_DATA_UNAVAILABLE_MESSAGE,
    MarketDataProvider,
    MarketDataUnavailableError,
)


async def get_market_quote_result(
    provider: MarketDataProvider,
    exchange: str,
    symbol_token: str,
) -> dict[str, object]:
    request = QuoteRequest(exchange=exchange, symbol_token=symbol_token)
    try:
        quote = await provider.get_quote(request)
    except MarketDataUnavailableError:
        raise RuntimeError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
    except Exception:
        raise RuntimeError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
    result = quote.to_public_dict()
    result["message"] = (
        "Read-only educational quote. This MCP server cannot place, modify, or "
        "cancel orders."
    )
    return result


async def search_market_instruments_result(
    provider: MarketDataProvider,
    query: str,
    exchange: str | None = None,
    limit: int = 5,
) -> list[dict[str, object]]:
    request = InstrumentSearchRequest(query=query, exchange=exchange, limit=limit)
    try:
        instruments = await provider.search_instruments(request)
    except MarketDataUnavailableError:
        raise RuntimeError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
    except Exception:
        raise RuntimeError(MARKET_DATA_UNAVAILABLE_MESSAGE) from None
    return [instrument.to_public_dict() for instrument in instruments]


def create_mcp_server(provider: MarketDataProvider | None = None) -> MCPServer:
    selected_provider = provider or create_market_data_provider()
    server = MCPServer(
        "FinEd Saathi Market Data",
        description="Read-only attributable Angel One market quotes for education.",
        instructions=(
            "Use quotes only to explain market concepts. State provider and exchange "
            "time. Never treat a quote as an order or investment recommendation."
        ),
    )

    @server.tool(
        name="get_market_quote",
        description=(
            "Get one timestamped NSE or BSE quote by Angel One numeric symbol token."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
        structured_output=True,
    )
    async def get_market_quote(exchange: str, symbol_token: str) -> dict[str, object]:
        return await get_market_quote_result(selected_provider, exchange, symbol_token)

    @server.tool(
        name="search_market_instruments",
        description=(
            "Search NSE or BSE instrument symbols by name. Results are read-only "
            "and cannot place, modify, or cancel orders."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
        structured_output=True,
    )
    async def search_market_instruments(
        query: str, exchange: str | None = None, limit: int = 5
    ) -> list[dict[str, object]]:
        return await search_market_instruments_result(
            selected_provider, query, exchange, limit
        )

    return server


def main() -> None:
    load_dotenv(".env.local")
    create_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
