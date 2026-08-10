from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fined.historical_returns import (
    HistoricalReturnInput,
    calculate_historical_return,
)
from fined.market_data.models import HistoricalClose, HistoricalPricePair


def prices(entry: str = "100", valuation: str = "125") -> HistoricalPricePair:
    return HistoricalPricePair(
        entry=HistoricalClose(date(2024, 1, 8), Decimal(entry)),
        valuation=HistoricalClose(date(2026, 8, 7), Decimal(valuation)),
        provider="Angel One SmartAPI",
    )


def test_historical_return_calculates_whole_units_and_public_caveats() -> None:
    # Catches fractional-share math or omission of the required estimate warnings.
    result = calculate_historical_return(
        HistoricalReturnInput(Decimal("10000"), prices())
    )

    assert result.units == 100
    assert result.leftover_cash == Decimal("0.00")
    assert result.final_value == Decimal("12500.00")
    assert result.absolute_return == Decimal("2500.00")
    assert result.percentage_return == Decimal("25.00")
    assert result.to_tool_result() == {
        "investment_amount": "10000.00",
        "entry_date": "2024-01-08",
        "entry_price": "100.00",
        "valuation_date": "2026-08-07",
        "valuation_price": "125.00",
        "units": 100,
        "invested_amount": "10000.00",
        "leftover_cash": "0.00",
        "final_value": "12500.00",
        "absolute_return": "2500.00",
        "percentage_return": "25.00",
        "provider": "Angel One SmartAPI",
        "price_basis": "unadjusted_daily_close",
        "adjusted_for_corporate_actions": False,
        "includes_dividends": False,
        "includes_fees_and_taxes": False,
        "includes_inflation": False,
        "is_forecast": False,
        "is_recommendation": False,
        "is_order": False,
        "message": (
            "Historical illustration using whole units and unadjusted daily closing "
            "prices. Dividends, splits, bonus issues, fees, taxes and inflation "
            "are excluded. This is not a total-return figure, forecast or "
            "recommendation."
        ),
    }


def test_historical_return_preserves_leftover_cash() -> None:
    # Catches treating Indian cash equities as fractionally purchasable.
    result = calculate_historical_return(
        HistoricalReturnInput(Decimal("1000"), prices("333", "400"))
    )

    assert result.units == 3
    assert result.invested_amount == Decimal("999.00")
    assert result.leftover_cash == Decimal("1.00")
    assert result.final_value == Decimal("1201.00")
    assert result.absolute_return == Decimal("201.00")
    assert result.percentage_return == Decimal("20.10")


def test_historical_return_handles_loss_and_unaffordable_unit() -> None:
    # Catches forcing returns positive or fabricating exposure when no unit fits.
    loss = calculate_historical_return(
        HistoricalReturnInput(Decimal("1000"), prices("400", "350"))
    )
    unaffordable = calculate_historical_return(
        HistoricalReturnInput(Decimal("100"), prices("500", "700"))
    )

    assert loss.units == 2
    assert loss.final_value == Decimal("900.00")
    assert loss.absolute_return == Decimal("-100.00")
    assert loss.percentage_return == Decimal("-10.00")
    assert unaffordable.units == 0
    assert unaffordable.leftover_cash == Decimal("100.00")
    assert unaffordable.final_value == Decimal("100.00")
    assert unaffordable.percentage_return == Decimal("0.00")


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("0"),
        Decimal("-1"),
        Decimal("0.001"),
        Decimal("100000000.01"),
    ],
)
def test_historical_return_rejects_nonfinite_or_out_of_range_amounts(
    amount: Decimal,
) -> None:
    # Catches unsafe Decimal arithmetic and unbounded model-supplied values.
    with pytest.raises(ValueError, match="investment amount"):
        HistoricalReturnInput(amount, prices())
