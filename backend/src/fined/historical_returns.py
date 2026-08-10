from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fined.market_data.models import HistoricalPricePair

_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")
_MIN_INVESTMENT = Decimal("0.01")
_MAX_INVESTMENT = Decimal("100000000.00")
_HISTORICAL_WARNING = (
    "Historical illustration using whole units and unadjusted daily closing "
    "prices. Dividends, splits, bonus issues, fees, taxes and inflation are "
    "excluded. This is not a total-return figure, forecast or recommendation."
)


@dataclass(frozen=True)
class HistoricalReturnInput:
    investment_amount: Decimal
    prices: HistoricalPricePair

    def __post_init__(self) -> None:
        validate_historical_investment_amount(self.investment_amount)
        if not isinstance(self.prices, HistoricalPricePair):
            raise ValueError("historical prices are invalid")


@dataclass(frozen=True)
class HistoricalReturnResult:
    investment_amount: Decimal
    prices: HistoricalPricePair
    units: int
    invested_amount: Decimal
    leftover_cash: Decimal
    final_value: Decimal
    absolute_return: Decimal
    percentage_return: Decimal

    def to_tool_result(self) -> dict[str, object]:
        return {
            "investment_amount": _money_text(self.investment_amount),
            "entry_date": self.prices.entry.trading_date.isoformat(),
            "entry_price": _money_text(self.prices.entry.close_price),
            "valuation_date": self.prices.valuation.trading_date.isoformat(),
            "valuation_price": _money_text(self.prices.valuation.close_price),
            "units": self.units,
            "invested_amount": _money_text(self.invested_amount),
            "leftover_cash": _money_text(self.leftover_cash),
            "final_value": _money_text(self.final_value),
            "absolute_return": _money_text(self.absolute_return),
            "percentage_return": _money_text(self.percentage_return),
            "provider": self.prices.provider,
            "price_basis": "unadjusted_daily_close",
            "adjusted_for_corporate_actions": False,
            "includes_dividends": False,
            "includes_fees_and_taxes": False,
            "includes_inflation": False,
            "is_forecast": False,
            "is_recommendation": False,
            "is_order": False,
            "message": _HISTORICAL_WARNING,
        }


def calculate_historical_return(
    value: HistoricalReturnInput,
) -> HistoricalReturnResult:
    amount = value.investment_amount.quantize(_MONEY, rounding=ROUND_HALF_UP)
    entry_price = value.prices.entry.close_price
    valuation_price = value.prices.valuation.close_price
    units = int((amount / entry_price).to_integral_value(rounding=ROUND_FLOOR))
    invested_amount = _money(entry_price * units)
    leftover_cash = _money(amount - invested_amount)
    final_value = _money(valuation_price * units + leftover_cash)
    absolute_return = _money(final_value - amount)
    percentage_return = (absolute_return / amount * Decimal("100")).quantize(
        _PERCENT, rounding=ROUND_HALF_UP
    )
    return HistoricalReturnResult(
        investment_amount=amount,
        prices=value.prices,
        units=units,
        invested_amount=invested_amount,
        leftover_cash=leftover_cash,
        final_value=final_value,
        absolute_return=absolute_return,
        percentage_return=percentage_return,
    )


def validate_historical_investment_amount(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("investment amount must be a finite decimal")
    if not _MIN_INVESTMENT <= value <= _MAX_INVESTMENT:
        raise ValueError("investment amount is outside the supported range")
    if value.quantize(_MONEY, rounding=ROUND_HALF_UP) != value:
        raise ValueError("investment amount supports at most two decimal places")
    return value


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal) -> str:
    return format(_money(value), "f")
