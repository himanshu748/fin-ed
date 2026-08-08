from __future__ import annotations

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from fined.market_data.angel_one import create_market_data_provider
from fined.market_data.models import QuoteRequest
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

    return server


def main() -> None:
    load_dotenv(".env.local")
    create_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
