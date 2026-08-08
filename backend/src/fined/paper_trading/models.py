"""Strict, public-only contracts for the paper-trading browser boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from fined.market_data.models import SUPPORTED_EXCHANGES

PaperSide = Literal["buy", "sell"]
PaperChargeStatus = Literal["estimated", "unavailable"]

RPC_VERSION = 1
MAX_RPC_PAYLOAD_BYTES = 15_000
PAPER_DRAFT_LIFETIME = timedelta(seconds=30)

_SYMBOL_TOKEN = re.compile(r"^[0-9]{1,20}$")
_SIDES = frozenset({"buy", "sell"})
_CHARGE_STATUSES = frozenset({"estimated", "unavailable"})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _require_non_negative_paise(value: object, field_name: str) -> int:
    if not _is_int(value) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative whole number of paise")
    return value


def _require_timestamp(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO timestamp") from error
    return _require_timestamp(parsed, field_name)


def _encode_payload(payload: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_RPC_PAYLOAD_BYTES:
        raise ValueError("paper RPC payload exceeds the maximum size")
    return dict(payload)


def _decode_json(payload: str) -> Mapping[str, object]:
    if (
        not isinstance(payload, str)
        or len(payload.encode("utf-8")) > MAX_RPC_PAYLOAD_BYTES
    ):
        raise ValueError("paper RPC payload exceeds the maximum size")
    try:
        decoded = json.loads(
            payload,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid JSON")),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("paper RPC payload must be valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("paper RPC payload must be an object")
    return decoded


def _require_exact_keys(
    payload: Mapping[str, object], expected: frozenset[str]
) -> None:
    if set(payload) != expected:
        raise ValueError("paper RPC payload has an invalid shape")


def _require_paper_envelope(payload: Mapping[str, object]) -> None:
    version = payload.get("version")
    if (
        not _is_int(version)
        or version != RPC_VERSION
        or payload.get("paper") is not True
    ):
        raise ValueError("paper RPC payload has an unsupported version")


@dataclass(frozen=True)
class PaperOrderDraft:
    draft_id: str
    side: PaperSide
    exchange: str
    symbol_token: str
    trading_symbol: str
    quantity: int
    price_paise: int
    quote_provider: str
    quote_time: datetime
    expires_at: datetime
    notional_paise: int
    charge_paise: int | None
    cash_effect_paise: int | None
    charge_status: PaperChargeStatus

    def __post_init__(self) -> None:
        _require_non_empty_text(self.draft_id, "draft id")
        if not isinstance(self.side, str) or self.side not in _SIDES:
            raise ValueError("paper side must be buy or sell")
        if (
            not isinstance(self.exchange, str)
            or self.exchange not in SUPPORTED_EXCHANGES
        ):
            raise ValueError("exchange must be NSE or BSE")
        if not isinstance(self.symbol_token, str) or not _SYMBOL_TOKEN.fullmatch(
            self.symbol_token
        ):
            raise ValueError("symbol token must contain 1 to 20 ASCII digits")
        _require_non_empty_text(self.trading_symbol, "trading symbol")
        if not _is_int(self.quantity) or self.quantity <= 0:
            raise ValueError("quantity must be a positive whole number")
        if not _is_int(self.price_paise) or self.price_paise <= 0:
            raise ValueError(
                "quote price must be a finite positive whole number of paise"
            )
        _require_non_empty_text(self.quote_provider, "quote provider")
        quote_time = _require_timestamp(self.quote_time, "quote time")
        expires_at = _require_timestamp(self.expires_at, "expiry time")
        if expires_at - quote_time != PAPER_DRAFT_LIFETIME:
            raise ValueError(
                "paper draft expiry must be exactly 30 seconds after the quote"
            )
        notional_paise = _require_non_negative_paise(
            self.notional_paise, "notional paise"
        )
        expected_notional = self.quantity * self.price_paise
        if notional_paise != expected_notional:
            raise ValueError("notional paise must equal quantity times price paise")
        if (
            not isinstance(self.charge_status, str)
            or self.charge_status not in _CHARGE_STATUSES
        ):
            raise ValueError("charge status must be estimated or unavailable")
        if self.charge_status == "estimated":
            charge_paise = _require_non_negative_paise(
                self.charge_paise, "charge paise"
            )
            if not _is_int(self.cash_effect_paise):
                raise ValueError("cash effect paise must be a whole number")
            expected_cash_effect = (
                -(self.notional_paise + charge_paise)
                if self.side == "buy"
                else self.notional_paise - charge_paise
            )
            if self.cash_effect_paise != expected_cash_effect:
                raise ValueError("cash effect paise is inconsistent with the draft")
        elif self.charge_paise is not None or self.cash_effect_paise is not None:
            raise ValueError(
                "unavailable charges must not include charge or cash effect"
            )

        # Validate the actual public object, including UTF-8 expansion, before it
        # can cross the RPC boundary.
        self.to_rpc_payload()

    def to_rpc_payload(self) -> dict[str, object]:
        return _encode_payload(
            {
                "version": RPC_VERSION,
                "paper": True,
                "draft_id": self.draft_id,
                "side": self.side,
                "exchange": self.exchange,
                "symbol_token": self.symbol_token,
                "trading_symbol": self.trading_symbol,
                "quantity": self.quantity,
                "price_paise": self.price_paise,
                "quote_provider": self.quote_provider,
                "quote_time": self.quote_time.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "notional_paise": self.notional_paise,
                "charge_paise": self.charge_paise,
                "cash_effect_paise": self.cash_effect_paise,
                "charge_status": self.charge_status,
            }
        )


@dataclass(frozen=True)
class PaperPortfolioSummary:
    cash_paise: int
    holdings_cost_basis_paise: int
    cash_plus_cost_basis_paise: int

    def __post_init__(self) -> None:
        cash = _require_non_negative_paise(self.cash_paise, "cash paise")
        holdings_cost_basis = _require_non_negative_paise(
            self.holdings_cost_basis_paise, "holdings cost basis paise"
        )
        cash_plus_cost_basis = _require_non_negative_paise(
            self.cash_plus_cost_basis_paise, "cash plus cost basis paise"
        )
        if cash_plus_cost_basis != cash + holdings_cost_basis:
            raise ValueError(
                "cash plus cost basis paise must equal cash plus holdings cost basis"
            )

    def to_rpc_payload(self) -> dict[str, object]:
        return _encode_payload(
            {
                "version": RPC_VERSION,
                "paper": True,
                "cash_paise": self.cash_paise,
                "holdings_cost_basis_paise": self.holdings_cost_basis_paise,
                "cash_plus_cost_basis_paise": self.cash_plus_cost_basis_paise,
            }
        )


@dataclass(frozen=True)
class PaperDashboardAck:
    opened: bool

    def __post_init__(self) -> None:
        if not isinstance(self.opened, bool):
            raise ValueError("opened must be a boolean")


@dataclass(frozen=True)
class PaperDraftAck:
    prepared: bool
    draft_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.prepared, bool):
            raise ValueError("prepared must be a boolean")
        _require_non_empty_text(self.draft_id, "draft id")


@dataclass(frozen=True)
class PaperOrderResult:
    draft_id: str
    side: PaperSide
    trading_symbol: str
    quantity: int
    fill_price_paise: int
    simulated_at: datetime
    cash_paise: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.draft_id, "draft id")
        if not isinstance(self.side, str) or self.side not in _SIDES:
            raise ValueError("paper side must be buy or sell")
        _require_non_empty_text(self.trading_symbol, "trading symbol")
        if not _is_int(self.quantity) or self.quantity <= 0:
            raise ValueError("quantity must be a positive whole number")
        if not _is_int(self.fill_price_paise) or self.fill_price_paise <= 0:
            raise ValueError(
                "fill price must be a finite positive whole number of paise"
            )
        _require_timestamp(self.simulated_at, "simulated time")
        _require_non_negative_paise(self.cash_paise, "cash paise")

    def to_rpc_payload(self) -> dict[str, object]:
        return _encode_payload(
            {
                "version": RPC_VERSION,
                "paper": True,
                "draft_id": self.draft_id,
                "side": self.side,
                "trading_symbol": self.trading_symbol,
                "quantity": self.quantity,
                "fill_price_paise": self.fill_price_paise,
                "simulated_at": self.simulated_at.isoformat(),
                "cash_paise": self.cash_paise,
            }
        )


def decode_paper_dashboard_ack(payload: str) -> PaperDashboardAck:
    decoded = _decode_json(payload)
    _require_exact_keys(decoded, frozenset({"version", "paper", "opened"}))
    _require_paper_envelope(decoded)
    return PaperDashboardAck(opened=decoded["opened"])


def decode_paper_draft_ack(payload: str) -> PaperDraftAck:
    decoded = _decode_json(payload)
    _require_exact_keys(
        decoded, frozenset({"version", "paper", "prepared", "draft_id"})
    )
    _require_paper_envelope(decoded)
    return PaperDraftAck(prepared=decoded["prepared"], draft_id=decoded["draft_id"])


def decode_paper_portfolio_summary(payload: str) -> PaperPortfolioSummary:
    decoded = _decode_json(payload)
    _require_exact_keys(
        decoded,
        frozenset(
            {
                "version",
                "paper",
                "cash_paise",
                "holdings_cost_basis_paise",
                "cash_plus_cost_basis_paise",
            }
        ),
    )
    _require_paper_envelope(decoded)
    return PaperPortfolioSummary(
        cash_paise=decoded["cash_paise"],
        holdings_cost_basis_paise=decoded["holdings_cost_basis_paise"],
        cash_plus_cost_basis_paise=decoded["cash_plus_cost_basis_paise"],
    )


def decode_paper_order_result(payload: str) -> PaperOrderResult:
    decoded = _decode_json(payload)
    _require_exact_keys(
        decoded,
        frozenset(
            {
                "version",
                "paper",
                "draft_id",
                "side",
                "trading_symbol",
                "quantity",
                "fill_price_paise",
                "simulated_at",
                "cash_paise",
            }
        ),
    )
    _require_paper_envelope(decoded)
    return PaperOrderResult(
        draft_id=decoded["draft_id"],
        side=decoded["side"],
        trading_symbol=decoded["trading_symbol"],
        quantity=decoded["quantity"],
        fill_price_paise=decoded["fill_price_paise"],
        simulated_at=_parse_timestamp(decoded["simulated_at"], "simulated time"),
        cash_paise=decoded["cash_paise"],
    )
