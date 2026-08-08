import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest

from fined.calculator import (
    DeliveryFill,
    DeliveryTrade,
    ScheduleConfigurationError,
    UnsupportedScheduleError,
    calculate_delivery_fill,
    calculate_delivery_trade,
    validate_schedule_data,
)


def nse_trade(**overrides: object) -> DeliveryTrade:
    values: dict[str, object] = {
        "trade_date": date(2026, 8, 6),
        "exchange": "NSE",
        "quantity": 1,
        "buy_price": Decimal("6"),
        "sell_price": Decimal("6"),
        "brokerage_promotion_applies": False,
    }
    values.update(overrides)
    return DeliveryTrade(**values)  # type: ignore[arg-type]


def schedule_data() -> dict[str, object]:
    schedule_file = resources.files("fined.data").joinpath("angel_one_schedules.json")
    return json.loads(schedule_file.read_text(encoding="utf-8"))


def six_rupee_ui_fixture() -> dict[str, object]:
    fixture_file = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "data"
        / "six-rupee-delivery.json"
    )
    return json.loads(fixture_file.read_text(encoding="utf-8"))


def test_same_price_micro_trade_loses_money_only_to_costs():
    result = calculate_delivery_trade(nse_trade())

    assert result.gross_pnl == Decimal("0.00")
    assert result.total_charges > Decimal("0.00")
    assert result.net_pnl == -result.total_charges
    assert result.brokerage_buy == Decimal("5.00")
    assert result.brokerage_sell == Decimal("5.00")
    assert result.dp_charge == Decimal("20.00")
    assert result.gst > Decimal("5.40")
    assert result.total_charges == Decimal("35.41")
    assert result.is_estimate is True


def test_six_rupee_ui_fixture_matches_the_deterministic_calculator() -> None:
    fixture = six_rupee_ui_fixture()
    assumptions = fixture["assumptions"]
    assert isinstance(assumptions, dict)
    trade = DeliveryTrade(
        trade_date=date.fromisoformat(str(assumptions["trade_date"])),
        exchange=str(assumptions["exchange"]),  # type: ignore[arg-type]
        quantity=int(assumptions["quantity"]),
        buy_price=Decimal(str(assumptions["buy_price"])),
        sell_price=Decimal(str(assumptions["sell_price"])),
        executed_buy_orders=int(assumptions["executed_buy_orders"]),
        executed_sell_orders=int(assumptions["executed_sell_orders"]),
        demat_debits=int(assumptions["demat_debits"]),
        brokerage_promotion_applies=bool(assumptions["brokerage_promotion_applies"]),
    )
    result = calculate_delivery_trade(trade)

    assert fixture["historical_loss_status"] == "unresolved"
    assert fixture["result"] == {
        "brokerage_buy": str(result.brokerage_buy.quantize(Decimal("0.01"))),
        "brokerage_sell": str(result.brokerage_sell.quantize(Decimal("0.01"))),
        "dp_charge_before_gst": str(result.dp_charge.quantize(Decimal("0.01"))),
        "total_charges": str(result.total_charges),
        "net_pnl": str(result.net_pnl),
        "fee_to_investment_percent": str(result.fee_to_investment_percent),
        "break_even_sell_price": str(result.break_even_sell_price),
    }


def test_packaged_schedule_names_sebi_stamp_and_turnover_sources_truthfully() -> None:
    schedule = schedule_data()["schedules"][0]  # type: ignore[index]
    sources = {source["url"]: source["title"] for source in schedule["sources"]}  # type: ignore[index]

    assert (
        sources["https://www.sebi.gov.in/sebi_data/faqfiles/sep-2020/1599820228476.pdf"]
        == "SEBI FAQ on Indian Stamp Act amendments"
    )
    assert (
        sources["https://www.sebi.gov.in/sebi_data/commondocs/stockbroamendregu_p.pdf"]
        == "SEBI Stock Brokers Regulations, Schedule V"
    )


def test_displayed_net_pnl_reconciles_to_displayed_gross_pnl_less_charges():
    result = calculate_delivery_trade(
        nse_trade(buy_price=Decimal("0.001"), sell_price=Decimal("0.006"))
    )

    assert result.gross_pnl is not None
    assert result.net_pnl == result.gross_pnl - result.total_charges


def test_break_even_is_above_buy_price():
    result = calculate_delivery_trade(nse_trade())

    assert result.break_even_sell_price is not None
    assert result.break_even_sell_price > Decimal("6.00")


def test_quantity_must_be_positive():
    with pytest.raises(ValueError, match="quantity"):
        nse_trade(quantity=0)


def test_buy_only_trade_has_no_sell_side_or_dp_charge():
    result = calculate_delivery_trade(nse_trade(sell_price=None))

    assert result.gross_sell_value is None
    assert result.gross_pnl is None
    assert result.brokerage_sell == Decimal("0")
    assert result.dp_charge == Decimal("0")
    assert result.net_pnl is None
    assert result.break_even_sell_price is None


def test_bse_allowlisted_group_uses_its_group_rate():
    result = calculate_delivery_trade(nse_trade(exchange="BSE", bse_group="A"))

    assert result.exchange_charge == Decimal("0.000450")


def test_bse_without_scrip_group_is_rejected_with_correctable_message():
    with pytest.raises(ValueError, match=r"BSE.*group"):
        calculate_delivery_trade(nse_trade(exchange="BSE"))


def test_promotion_uncertainty_is_called_out_as_an_estimate():
    result = calculate_delivery_trade(nse_trade(brokerage_promotion_applies=None))

    assert result.brokerage_buy == Decimal("5.00")
    assert any("promotion" in reason.lower() for reason in result.estimate_reasons)


def test_promotion_waives_no_more_than_its_500_rupee_credit_cap():
    result = calculate_delivery_trade(
        nse_trade(
            quantity=300_000,
            buy_price=Decimal("1"),
            sell_price=Decimal("1"),
            executed_buy_orders=30,
            executed_sell_orders=30,
            brokerage_promotion_applies=True,
        )
    )

    assert result.brokerage_buy == Decimal("0")
    assert result.brokerage_sell == Decimal("100.000")


def test_each_executed_order_receives_the_minimum_brokerage():
    result = calculate_delivery_trade(nse_trade(executed_buy_orders=2))

    assert result.brokerage_buy == Decimal("10.00")


def test_each_demat_debit_increases_dp_charge_and_its_gst():
    result = calculate_delivery_trade(nse_trade(demat_debits=2))

    assert result.dp_charge == Decimal("40.00")
    assert result.gst > Decimal("9.00")


def test_no_demat_debit_has_no_dp_charge():
    result = calculate_delivery_trade(nse_trade(demat_debit=False))

    assert result.dp_charge == Decimal("0")


def test_pre_schedule_date_is_not_silently_priced_at_current_rates():
    with pytest.raises(UnsupportedScheduleError):
        calculate_delivery_trade(nse_trade(trade_date=date(2026, 2, 28)))


def test_schedule_validation_rejects_a_numeric_rate_value():
    data = schedule_data()
    schedule = data["schedules"][0]  # type: ignore[index]
    schedule["nse_transaction_rate_each_side"] = 1  # type: ignore[index]

    with pytest.raises(ScheduleConfigurationError, match="nse_transaction_rate"):
        validate_schedule_data(data)


def test_schedule_validation_rejects_overlapping_date_ranges():
    data = schedule_data()
    schedules = data["schedules"]  # type: ignore[index]
    overlapping = deepcopy(schedules[0])  # type: ignore[index]
    overlapping["effective_from"] = "2026-08-01"
    schedules.append(overlapping)  # type: ignore[union-attr]

    with pytest.raises(ScheduleConfigurationError, match="overlap"):
        validate_schedule_data(data)


def test_schedule_validation_accepts_adjacent_nonoverlapping_date_ranges():
    data = schedule_data()
    schedules = data["schedules"]  # type: ignore[index]
    schedules[0]["effective_to"] = "2026-07-31"  # type: ignore[index]
    next_schedule = deepcopy(schedules[0])  # type: ignore[index]
    next_schedule["effective_from"] = "2026-08-01"
    next_schedule["effective_to"] = None
    schedules.append(next_schedule)  # type: ignore[union-attr]

    assert validate_schedule_data(data) is data


def test_tool_result_serializes_decimals_dates_reasons_and_sources():
    result = calculate_delivery_trade(nse_trade())

    tool_result = result.to_tool_result()

    assert tool_result["total_charges"] == "35.41"
    assert tool_result["schedule_effective_from"] == "2026-03-01"
    assert isinstance(tool_result["gst"], str)
    assert tool_result["estimate_reasons"] == list(result.estimate_reasons)
    assert tool_result["schedule_sources"][0]["title"]
    assert tool_result["schedule_sources"][0]["url"].startswith("https://")


def test_buy_fill_contains_no_dp_charge() -> None:
    result = calculate_delivery_fill(
        DeliveryFill(
            side="buy",
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=1,
            price=Decimal("100"),
        )
    )

    assert result.notional == Decimal("100.00")
    assert result.dp_charge == Decimal("0")
    assert result.cash_effect == -(result.notional + result.total_charges)


def test_sell_fill_contains_one_demat_debit() -> None:
    result = calculate_delivery_fill(
        DeliveryFill(
            side="sell",
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=1,
            price=Decimal("100"),
        )
    )

    assert result.dp_charge == Decimal("20.00")
    assert result.cash_effect == result.notional - result.total_charges


def test_bse_fill_requires_a_scrip_group() -> None:
    with pytest.raises(ValueError, match=r"BSE.*group"):
        DeliveryFill(
            side="buy",
            trade_date=date(2026, 8, 8),
            exchange="BSE",
            quantity=1,
            price=Decimal("100"),
        )


def test_fill_promotion_uncertainty_is_called_out_as_an_estimate() -> None:
    result = calculate_delivery_fill(
        DeliveryFill(
            side="buy",
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=1,
            price=Decimal("100"),
            brokerage_promotion_applies=None,
        )
    )

    assert result.brokerage == Decimal("5.00")
    assert any("promotion" in reason.lower() for reason in result.estimate_reasons)


def test_fill_rejects_promotion_without_remaining_account_credit() -> None:
    with pytest.raises(ValueError, match="remaining account-level promotion credit"):
        calculate_delivery_fill(
            DeliveryFill(
                side="buy",
                trade_date=date(2026, 8, 8),
                exchange="NSE",
                quantity=1,
                price=Decimal("100"),
                brokerage_promotion_applies=True,
            )
        )


def test_fill_side_must_be_buy_or_sell() -> None:
    with pytest.raises(ValueError, match="side"):
        DeliveryFill(
            side="hold",  # type: ignore[arg-type]
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=1,
            price=Decimal("100"),
        )


def test_fill_quantity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="quantity"):
        DeliveryFill(
            side="buy",
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=0,
            price=Decimal("100"),
        )


def test_fill_pre_schedule_date_is_not_silently_priced_at_current_rates() -> None:
    with pytest.raises(UnsupportedScheduleError):
        calculate_delivery_fill(
            DeliveryFill(
                side="buy",
                trade_date=date(2026, 2, 28),
                exchange="NSE",
                quantity=1,
                price=Decimal("100"),
            )
        )


def test_fill_tool_result_serializes_decimals_dates_reasons_and_sources() -> None:
    result = calculate_delivery_fill(
        DeliveryFill(
            side="sell",
            trade_date=date(2026, 8, 8),
            exchange="NSE",
            quantity=1,
            price=Decimal("100"),
        )
    )

    tool_result = result.to_tool_result()

    assert tool_result["notional"] == "100.00"
    assert isinstance(tool_result["cash_effect"], str)
    assert tool_result["schedule_effective_from"] == "2026-03-01"
    assert tool_result["estimate_reasons"] == list(result.estimate_reasons)
    assert tool_result["schedule_sources"][0]["title"]
    assert tool_result["schedule_sources"][0]["url"].startswith("https://")
