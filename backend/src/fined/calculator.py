"""Deterministic, illustrative equity-delivery charge calculations for Angel One."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from importlib import resources
from typing import Any, Literal

PAISE = Decimal("0.01")
HUNDRED = Decimal("100")
BSE_GROUPS = frozenset(
    {
        "A",
        "B",
        "E",
        "F",
        "FC",
        "G",
        "GC",
        "I",
        "W",
        "T",
        "M",
        "MT",
        "MS",
        "TS",
        "IF",
        "IT",
        "XC",
        "XD",
        "XT",
        "Z",
        "ZP",
        "P",
        "R",
        "SS",
        "ST",
    }
)
DECIMAL_SCHEDULE_KEYS = (
    "delivery_brokerage_rate",
    "delivery_brokerage_cap",
    "delivery_brokerage_minimum",
    "new_account_brokerage_credit_cap",
    "dp_charge_before_gst",
    "stt_delivery_rate_each_side",
    "stamp_duty_delivery_buy_rate",
    "sebi_turnover_rate_each_side",
    "nse_transaction_rate_each_side",
    "nse_ipft_rate_each_side",
    "gst_rate",
)
REQUIRED_SCHEDULE_KEYS = (
    "effective_from",
    "effective_to",
    "brokerage_rule_effective_from",
    "statutory_exchange_rates_effective_from",
    "new_account_promotion_days",
    "bse_transaction_rates",
    "sources",
    *DECIMAL_SCHEDULE_KEYS,
)


class UnsupportedScheduleError(ValueError):
    """Raised when no verified schedule covers the requested trade date."""


class ScheduleConfigurationError(ValueError):
    """Raised when packaged fee schedule data is incomplete or internally invalid."""


@dataclass(frozen=True)
class ScheduleSource:
    title: str
    url: str


@dataclass(frozen=True)
class DeliveryTrade:
    trade_date: date
    exchange: Literal["NSE", "BSE"]
    quantity: int
    buy_price: Decimal
    sell_price: Decimal | None = None
    demat_debit: bool = True
    brokerage_promotion_applies: bool | None = None
    executed_buy_orders: int = 1
    executed_sell_orders: int = 1
    demat_debits: int = 1
    bse_group: str | None = None

    def __post_init__(self) -> None:
        if self.exchange not in ("NSE", "BSE"):
            raise ValueError("exchange must be NSE or BSE")
        if (
            not isinstance(self.quantity, int)
            or isinstance(self.quantity, bool)
            or self.quantity <= 0
        ):
            raise ValueError("quantity must be a positive integer")
        _require_positive_decimal("buy_price", self.buy_price)
        if self.sell_price is not None:
            _require_positive_decimal("sell_price", self.sell_price)
        for name in ("executed_buy_orders", "executed_sell_orders", "demat_debits"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.exchange == "BSE" and not self.bse_group:
            raise ValueError("BSE trades require an allowlisted BSE scrip group")


@dataclass(frozen=True)
class ChargeBreakdown:
    gross_buy_value: Decimal
    gross_sell_value: Decimal | None
    gross_pnl: Decimal | None
    brokerage_buy: Decimal
    brokerage_sell: Decimal
    dp_charge: Decimal
    stt: Decimal
    stamp_duty: Decimal
    exchange_charge: Decimal
    sebi_charge: Decimal
    gst: Decimal
    total_charges: Decimal
    net_pnl: Decimal | None
    fee_to_investment_percent: Decimal
    break_even_sell_price: Decimal | None
    is_estimate: bool
    estimate_reasons: tuple[str, ...]
    schedule_sources: tuple[ScheduleSource, ...]
    schedule_effective_from: date
    rounding_note: str

    def to_tool_result(self) -> dict[str, Any]:
        """Return a JSON-compatible representation without losing Decimal precision."""
        result: dict[str, Any] = {}
        for field_name, value in self.__dict__.items():
            if isinstance(value, Decimal):
                result[field_name] = _decimal_string(value)
            elif isinstance(value, date):
                result[field_name] = value.isoformat()
            elif isinstance(value, tuple) and field_name == "schedule_sources":
                result[field_name] = [
                    {"title": source.title, "url": source.url} for source in value
                ]
            elif isinstance(value, tuple):
                result[field_name] = list(value)
            else:
                result[field_name] = value
        return result


@dataclass(frozen=True)
class _RawCharges:
    gross_buy_value: Decimal
    gross_sell_value: Decimal | None
    gross_pnl: Decimal | None
    brokerage_buy: Decimal
    brokerage_sell: Decimal
    dp_charge: Decimal
    stt: Decimal
    stamp_duty: Decimal
    exchange_charge: Decimal
    sebi_charge: Decimal
    gst: Decimal
    total_charges: Decimal
    net_pnl: Decimal | None


def calculate_delivery_trade(trade: DeliveryTrade) -> ChargeBreakdown:
    """Calculate a schedule-backed illustrative delivery estimate for one trade."""
    schedule = _schedule_for(trade.trade_date)
    _validate_bse_group(trade, schedule)
    raw = _calculate_raw(trade, schedule)
    fee_percent = raw.total_charges / raw.gross_buy_value * HUNDRED
    reasons = [
        "Illustrative estimate: Angel One bills at contract-note and ledger aggregation levels that these inputs do not reproduce."
    ]
    if trade.brokerage_promotion_applies is None:
        reasons.append(
            "Brokerage promotion applicability was not provided; this estimate uses standard post-promotion brokerage."
        )
    break_even = (
        _break_even_sell_price(trade, schedule)
        if trade.sell_price is not None
        else None
    )
    sources = tuple(ScheduleSource(**source) for source in schedule["sources"])
    displayed_gross_pnl = _money(raw.gross_pnl) if raw.gross_pnl is not None else None
    displayed_total_charges = _money(raw.total_charges)
    return ChargeBreakdown(
        gross_buy_value=_money(raw.gross_buy_value),
        gross_sell_value=_money(raw.gross_sell_value)
        if raw.gross_sell_value is not None
        else None,
        gross_pnl=displayed_gross_pnl,
        brokerage_buy=raw.brokerage_buy,
        brokerage_sell=raw.brokerage_sell,
        dp_charge=raw.dp_charge,
        stt=raw.stt,
        stamp_duty=raw.stamp_duty,
        exchange_charge=raw.exchange_charge,
        sebi_charge=raw.sebi_charge,
        gst=raw.gst,
        total_charges=displayed_total_charges,
        net_pnl=(
            displayed_gross_pnl - displayed_total_charges
            if displayed_gross_pnl is not None
            else None
        ),
        fee_to_investment_percent=_money(fee_percent),
        break_even_sell_price=break_even,
        is_estimate=True,
        estimate_reasons=tuple(reasons),
        schedule_sources=sources,
        schedule_effective_from=_as_date(schedule["effective_from"]),
        rounding_note="Displayed gross P&L and charges are rounded to paise (₹0.01) using ROUND_HALF_UP; displayed net P&L is their difference. Levy and break-even calculations retain Decimal precision.",
    )


def _calculate_raw(trade: DeliveryTrade, schedule: dict[str, Any]) -> _RawCharges:
    buy_value = Decimal(trade.quantity) * trade.buy_price
    sell_value = (
        Decimal(trade.quantity) * trade.sell_price
        if trade.sell_price is not None
        else None
    )
    brokerage_buy = _brokerage_for_leg(
        buy_value, trade.executed_buy_orders, trade, schedule
    )
    brokerage_sell = (
        _brokerage_for_leg(sell_value, trade.executed_sell_orders, trade, schedule)
        if sell_value is not None
        else Decimal("0")
    )
    brokerage_buy, brokerage_sell = _apply_brokerage_promotion(
        brokerage_buy, brokerage_sell, trade, schedule
    )
    sell_turnover = sell_value if sell_value is not None else Decimal("0")
    stt = (buy_value + sell_turnover) * _decimal(
        schedule["stt_delivery_rate_each_side"]
    )
    stamp_duty = buy_value * _decimal(schedule["stamp_duty_delivery_buy_rate"])
    transaction_rate, ipft_rate = _exchange_rates(trade, schedule)
    exchange_charge = (buy_value + sell_turnover) * (transaction_rate + ipft_rate)
    sebi_charge = (buy_value + sell_turnover) * _decimal(
        schedule["sebi_turnover_rate_each_side"]
    )
    dp_charge = (
        _decimal(schedule["dp_charge_before_gst"]) * Decimal(trade.demat_debits)
        if sell_value is not None and trade.demat_debit
        else Decimal("0")
    )
    contract_note_gst_base = (
        brokerage_buy + brokerage_sell + exchange_charge + sebi_charge
    )
    gst_rate = _decimal(schedule["gst_rate"])
    gst = contract_note_gst_base * gst_rate + dp_charge * gst_rate
    total_charges = (
        brokerage_buy
        + brokerage_sell
        + dp_charge
        + stt
        + stamp_duty
        + exchange_charge
        + sebi_charge
        + gst
    )
    gross_pnl = sell_value - buy_value if sell_value is not None else None
    net_pnl = gross_pnl - total_charges if gross_pnl is not None else None
    return _RawCharges(
        gross_buy_value=buy_value,
        gross_sell_value=sell_value,
        gross_pnl=gross_pnl,
        brokerage_buy=brokerage_buy,
        brokerage_sell=brokerage_sell,
        dp_charge=dp_charge,
        stt=stt,
        stamp_duty=stamp_duty,
        exchange_charge=exchange_charge,
        sebi_charge=sebi_charge,
        gst=gst,
        total_charges=total_charges,
        net_pnl=net_pnl,
    )


def _break_even_sell_price(trade: DeliveryTrade, schedule: dict[str, Any]) -> Decimal:
    """Find the lowest paise sell price whose raw calculation is not loss-making."""
    lower = trade.buy_price
    upper = max(trade.buy_price * Decimal("2"), trade.buy_price + Decimal("1"))
    while _calculate_raw(replace(trade, sell_price=upper), schedule).net_pnl < Decimal(
        "0"
    ):
        upper *= Decimal("2")
    for _ in range(128):
        middle = (lower + upper) / Decimal("2")
        if _calculate_raw(
            replace(trade, sell_price=middle), schedule
        ).net_pnl < Decimal("0"):
            lower = middle
        else:
            upper = middle
    candidate = upper.quantize(PAISE, rounding=ROUND_CEILING)
    while _calculate_raw(
        replace(trade, sell_price=candidate), schedule
    ).net_pnl < Decimal("0"):
        candidate += PAISE
    return candidate


def _brokerage_for_leg(
    turnover: Decimal,
    executed_orders: int,
    trade: DeliveryTrade,
    schedule: dict[str, Any],
) -> Decimal:
    per_order_turnover = turnover / Decimal(executed_orders)
    rate_charge = per_order_turnover * _decimal(schedule["delivery_brokerage_rate"])
    per_order_charge = min(
        _decimal(schedule["delivery_brokerage_cap"]),
        max(_decimal(schedule["delivery_brokerage_minimum"]), rate_charge),
    )
    return per_order_charge * Decimal(executed_orders)


def _apply_brokerage_promotion(
    brokerage_buy: Decimal,
    brokerage_sell: Decimal,
    trade: DeliveryTrade,
    schedule: dict[str, Any],
) -> tuple[Decimal, Decimal]:
    if trade.brokerage_promotion_applies is not True:
        return brokerage_buy, brokerage_sell
    credit = _decimal(schedule["new_account_brokerage_credit_cap"])
    credited_buy = min(brokerage_buy, credit)
    remaining_credit = credit - credited_buy
    credited_sell = min(brokerage_sell, remaining_credit)
    return brokerage_buy - credited_buy, brokerage_sell - credited_sell


def _exchange_rates(
    trade: DeliveryTrade, schedule: dict[str, Any]
) -> tuple[Decimal, Decimal]:
    if trade.exchange == "NSE":
        return (
            _decimal(schedule["nse_transaction_rate_each_side"]),
            _decimal(schedule["nse_ipft_rate_each_side"]),
        )
    return _decimal(
        schedule["bse_transaction_rates"][trade.bse_group.upper()]
    ), Decimal("0")


def _validate_bse_group(trade: DeliveryTrade, schedule: dict[str, Any]) -> None:
    if trade.exchange != "BSE":
        return
    group = trade.bse_group.upper() if trade.bse_group else ""
    if group not in schedule["bse_transaction_rates"]:
        raise ValueError(
            "BSE scrip group must be allowlisted because its transaction rate depends on the group"
        )


def _schedule_for(trade_date: date) -> dict[str, Any]:
    schedules = _load_schedules()["schedules"]
    for schedule in schedules:
        effective_from = _as_date(schedule["effective_from"])
        effective_to = (
            _as_date(schedule["effective_to"])
            if schedule["effective_to"] is not None
            else None
        )
        if trade_date >= effective_from and (
            effective_to is None or trade_date <= effective_to
        ):
            return schedule
    raise UnsupportedScheduleError(
        f"No verified Angel One schedule covers trade date {trade_date.isoformat()}"
    )


def _load_schedules() -> dict[str, Any]:
    schedule_file = resources.files("fined.data").joinpath("angel_one_schedules.json")
    try:
        data = json.loads(schedule_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScheduleConfigurationError(
            "Unable to load Angel One schedule data"
        ) from error
    return validate_schedule_data(data)


def validate_schedule_data(data: Any) -> dict[str, Any]:
    """Validate package data before it can be used for fee calculations."""
    if not isinstance(data, dict):
        raise ScheduleConfigurationError("Schedule data must be a JSON object")
    if not isinstance(data.get("broker"), str) or not data["broker"].strip():
        raise ScheduleConfigurationError("Schedule data requires a broker name")
    schedules = data.get("schedules")
    if not isinstance(schedules, list) or not schedules:
        raise ScheduleConfigurationError("Schedule data requires at least one schedule")

    date_ranges: list[tuple[date, date | None]] = []
    for index, schedule in enumerate(schedules):
        if not isinstance(schedule, dict):
            raise ScheduleConfigurationError(f"Schedule {index} must be an object")
        missing_keys = [key for key in REQUIRED_SCHEDULE_KEYS if key not in schedule]
        if missing_keys:
            raise ScheduleConfigurationError(
                f"Schedule {index} is missing required keys: {', '.join(missing_keys)}"
            )
        effective_from = _schedule_date(schedule["effective_from"], "effective_from")
        effective_to_value = schedule["effective_to"]
        effective_to = (
            _schedule_date(effective_to_value, "effective_to")
            if effective_to_value is not None
            else None
        )
        brokerage_from = _schedule_date(
            schedule["brokerage_rule_effective_from"], "brokerage_rule_effective_from"
        )
        statutory_from = _schedule_date(
            schedule["statutory_exchange_rates_effective_from"],
            "statutory_exchange_rates_effective_from",
        )
        if effective_to is not None and effective_to < effective_from:
            raise ScheduleConfigurationError(
                "Schedule effective_to precedes effective_from"
            )
        if brokerage_from > effective_from or statutory_from > effective_from:
            raise ScheduleConfigurationError("Schedule effective dates are not ordered")
        for key in DECIMAL_SCHEDULE_KEYS:
            _schedule_decimal(schedule[key], key)
        promotion_days = schedule["new_account_promotion_days"]
        if (
            not isinstance(promotion_days, int)
            or isinstance(promotion_days, bool)
            or promotion_days < 0
        ):
            raise ScheduleConfigurationError(
                "new_account_promotion_days must be a nonnegative integer"
            )
        _validate_bse_rate_allowlist(schedule["bse_transaction_rates"])
        _validate_sources(schedule["sources"])
        date_ranges.append((effective_from, effective_to))

    has_previous_range = False
    previous_end: date | None = None
    for effective_from, effective_to in sorted(date_ranges, key=lambda value: value[0]):
        if has_previous_range:
            if previous_end is None:
                raise ScheduleConfigurationError(
                    "Schedule date ranges overlap after an open-ended range"
                )
            if effective_from <= previous_end:
                raise ScheduleConfigurationError("Schedule date ranges overlap")
        previous_end = effective_to
        has_previous_range = True
    return data


def _schedule_date(value: Any, key: str) -> date:
    if not isinstance(value, str):
        raise ScheduleConfigurationError(f"{key} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ScheduleConfigurationError(f"{key} must be an ISO date string") from error


def _schedule_decimal(value: Any, key: str) -> Decimal:
    if not isinstance(value, str):
        raise ScheduleConfigurationError(f"{key} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ScheduleConfigurationError(f"{key} must be a decimal string") from error
    if not parsed.is_finite() or parsed < Decimal("0"):
        raise ScheduleConfigurationError(f"{key} must be a finite nonnegative decimal")
    return parsed


def _validate_bse_rate_allowlist(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != BSE_GROUPS:
        raise ScheduleConfigurationError("BSE transaction rate allowlist is malformed")
    for group, rate in value.items():
        if not isinstance(group, str) or group != group.upper():
            raise ScheduleConfigurationError(
                "BSE transaction rate allowlist is malformed"
            )
        _schedule_decimal(rate, f"bse_transaction_rates.{group}")


def _validate_sources(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ScheduleConfigurationError("Schedule source provenance is required")
    for source in value:
        if not isinstance(source, dict):
            raise ScheduleConfigurationError("Schedule source provenance is malformed")
        title, url = source.get("title"), source.get("url")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(url, str)
            or not url.startswith("https://")
        ):
            raise ScheduleConfigurationError("Schedule source provenance is malformed")


def _as_date(value: str) -> date:
    return date.fromisoformat(value)


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _decimal_string(value: Decimal) -> str:
    return format(value, "f")


def _require_positive_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= Decimal("0"):
        raise ValueError(f"{name} must be a positive Decimal")
