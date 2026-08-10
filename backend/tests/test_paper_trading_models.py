from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from fined.paper_trading.models import (
    MAX_RPC_PAYLOAD_BYTES,
    PaperHoldingQuote,
    PaperOrderDraft,
    PaperPortfolioSummary,
    decode_paper_dashboard_ack,
    decode_paper_draft_ack,
    decode_paper_holding_quote_request,
    decode_paper_order_result,
    decode_paper_portfolio_summary,
)


def paper_draft_fixture(**changes: object) -> PaperOrderDraft:
    fields: dict[str, object] = {
        "draft_id": "draft-1",
        "side": "buy",
        "exchange": "NSE",
        "symbol_token": "2885",
        "trading_symbol": "RELIANCE-EQ",
        "quantity": 2,
        "price_paise": 250_050,
        "quote_provider": "Angel One SmartAPI",
        "quote_time": datetime(2026, 8, 8, 9, 15, tzinfo=UTC),
        "expires_at": datetime(2026, 8, 8, 9, 15, 30, tzinfo=UTC),
        "notional_paise": 500_100,
        "charge_paise": 123,
        "cash_effect_paise": -500_223,
        "charge_status": "estimated",
    }
    fields.update(changes)
    return PaperOrderDraft(**fields)  # type: ignore[arg-type]


def test_draft_serializes_only_public_fields() -> None:
    draft = paper_draft_fixture()

    payload = draft.to_rpc_payload()

    assert payload["version"] == 1
    assert payload["paper"] is True
    assert payload["quote_provider"] == "Angel One SmartAPI"
    assert payload["quote_time"] == "2026-08-08T09:15:00+00:00"
    assert set(payload) == {
        "version",
        "paper",
        "draft_id",
        "side",
        "exchange",
        "symbol_token",
        "trading_symbol",
        "quantity",
        "price_paise",
        "quote_provider",
        "quote_time",
        "expires_at",
        "notional_paise",
        "charge_paise",
        "cash_effect_paise",
        "charge_status",
    }
    assert "access_token" not in json.dumps(payload).lower()


@pytest.mark.parametrize("side", ["BUY", "hold", "sell ", 1, ["buy"]])
def test_draft_rejects_non_paper_side_values(side: object) -> None:
    with pytest.raises(ValueError):
        paper_draft_fixture(side=side)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_draft_requires_a_positive_whole_quantity(quantity: object) -> None:
    with pytest.raises(ValueError):
        paper_draft_fixture(quantity=quantity)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol_token", "28A5"),
        ("exchange", "NFO"),
        ("price_paise", 0),
        ("price_paise", float("inf")),
        ("quote_time", datetime(2026, 8, 8, 9, 15)),
    ],
)
def test_draft_rejects_invalid_quote_contract(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        paper_draft_fixture(**{field: value})


def test_draft_requires_an_expiry_exactly_thirty_seconds_after_quote() -> None:
    quote_time = datetime(2026, 8, 8, 9, 15, tzinfo=UTC)

    with pytest.raises(ValueError):
        paper_draft_fixture(expires_at=quote_time + timedelta(seconds=29))


def test_draft_rejects_an_oversized_rpc_payload() -> None:
    with pytest.raises(ValueError):
        paper_draft_fixture(trading_symbol="R" * MAX_RPC_PAYLOAD_BYTES)


def test_draft_rejects_boolean_notional() -> None:
    with pytest.raises(ValueError):
        paper_draft_fixture(
            quantity=1,
            price_paise=1,
            notional_paise=True,
            charge_paise=0,
            cash_effect_paise=-1,
        )


def test_summary_rejects_negative_cash() -> None:
    with pytest.raises(ValueError):
        PaperPortfolioSummary(
            cash_paise=-1,
            holdings_cost_basis_paise=0,
            cash_plus_cost_basis_paise=0,
        )


def test_summary_rejects_an_inconsistent_total() -> None:
    with pytest.raises(ValueError):
        PaperPortfolioSummary(
            cash_paise=100,
            holdings_cost_basis_paise=20,
            cash_plus_cost_basis_paise=121,
        )


def test_decoders_reject_unknown_response_keys() -> None:
    response = json.dumps(
        {"version": 1, "paper": True, "opened": True, "access_token": "nope"}
    )

    with pytest.raises(ValueError):
        decode_paper_dashboard_ack(response)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
@pytest.mark.parametrize(
    ("decoder", "response"),
    [
        (decode_paper_dashboard_ack, {"paper": True, "opened": True}),
        (
            decode_paper_draft_ack,
            {"paper": True, "prepared": True, "draft_id": "draft-1"},
        ),
        (
            decode_paper_portfolio_summary,
            {
                "paper": True,
                "cash_paise": 10_000_000,
                "holdings_cost_basis_paise": 0,
                "cash_plus_cost_basis_paise": 10_000_000,
            },
        ),
        (
            decode_paper_order_result,
            {
                "paper": True,
                "draft_id": "draft-1",
                "side": "buy",
                "trading_symbol": "RELIANCE-EQ",
                "quantity": 1,
                "fill_price_paise": 250_050,
                "simulated_at": "2026-08-08T09:15:00+00:00",
                "cash_paise": 9_749_950,
            },
        ),
    ],
)
def test_every_response_decoder_rejects_non_integer_version(
    version: object, decoder: object, response: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        decoder(json.dumps({"version": version, **response}))  # type: ignore[operator]


def test_summary_decoder_accepts_only_the_versioned_public_shape() -> None:
    summary = decode_paper_portfolio_summary(
        json.dumps(
            {
                "version": 1,
                "paper": True,
                "cash_paise": 10_000_000,
                "holdings_cost_basis_paise": 250_000,
                "cash_plus_cost_basis_paise": 10_250_000,
            }
        )
    )

    assert summary.holdings_cost_basis_paise == 250_000
    assert summary.cash_plus_cost_basis_paise == 10_250_000


def test_summary_decoder_rejects_fields_that_claim_a_live_portfolio_value() -> None:
    with pytest.raises(ValueError):
        decode_paper_portfolio_summary(
            json.dumps(
                {
                    "version": 1,
                    "paper": True,
                    "cash_paise": 10_000_000,
                    "holdings_value_paise": 250_000,
                    "total_value_paise": 10_250_000,
                }
            )
        )


def test_browser_shaped_order_result_uses_a_python_310_compatible_utc_offset() -> None:
    payload = (
        '{"version":1,"paper":true,"draft_id":"draft-1","side":"buy",'
        '"trading_symbol":"RELIANCE-EQ","quantity":1,"fill_price_paise":250000,'
        '"simulated_at":"2026-08-08T00:00:10.000+00:00","cash_paise":9749900}'
    )

    result = decode_paper_order_result(payload)

    assert result.simulated_at == datetime(2026, 8, 8, 0, 0, 10, tzinfo=UTC)


def test_holding_quote_request_accepts_only_public_bounded_positions() -> None:
    request = decode_paper_holding_quote_request(
        '{"version":1,"paper":true,"holdings":[{"exchange":"NSE",'
        '"symbol_token":"11536","trading_symbol":"TCS-EQ","quantity":2}]}'
    )

    assert request[0].exchange == "NSE"
    assert request[0].symbol_token == "11536"
    assert request[0].quantity == 2

    with pytest.raises(ValueError):
        decode_paper_holding_quote_request(
            '{"version":1,"paper":true,"holdings":[{"exchange":"NSE",'
            '"symbol_token":"11536","trading_symbol":"TCS-EQ","quantity":2,'
            '"account_id":"secret"}]}'
        )


def test_holding_quote_response_contains_integer_paise_and_attribution() -> None:
    quote = PaperHoldingQuote(
        exchange="NSE",
        symbol_token="11536",
        trading_symbol="TCS-EQ",
        price_paise=246_660,
        quote_time=datetime(2026, 8, 10, 10, 34, 54, tzinfo=UTC),
        provider="Angel One SmartAPI",
    )

    assert quote.to_rpc_payload() == {
        "exchange": "NSE",
        "symbol_token": "11536",
        "trading_symbol": "TCS-EQ",
        "price_paise": 246_660,
        "quote_time": "2026-08-10T10:34:54+00:00",
        "provider": "Angel One SmartAPI",
    }
