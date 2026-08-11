"""Call-scoped virtual-money ledger for isolated outbound practice."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from .bridge import PaperTradingUIUnavailableError
from .models import (
    PaperDashboardAck,
    PaperDraftAck,
    PaperOrderDraft,
    PaperOrderResult,
    PaperPortfolioSummary,
)

PAPER_STARTING_CASH_PAISE = 10_000_000


@dataclass
class _Holding:
    quantity: int
    cost_basis_paise: int


class CallPaperTradingBridge:
    """Keep one non-persistent paper portfolio inside a single agent session."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._cash_paise = PAPER_STARTING_CASH_PAISE
        self._holdings: dict[tuple[str, str], _Holding] = {}
        self._drafts: dict[str, PaperOrderDraft] = {}
        self._applied_draft_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def open_dashboard(self) -> PaperDashboardAck:
        return PaperDashboardAck(opened=False)

    async def prepare_order(self, draft: PaperOrderDraft) -> PaperDraftAck:
        async with self._lock:
            now = self._current_time()
            if (
                draft.exchange != "NSE"
                or draft.expires_at <= now
                or draft.charge_status != "estimated"
                or draft.charge_paise is None
                or draft.cash_effect_paise is None
                or draft.draft_id in self._drafts
                or draft.draft_id in self._applied_draft_ids
            ):
                raise PaperTradingUIUnavailableError()
            self._drafts[draft.draft_id] = draft
            return PaperDraftAck(prepared=True, draft_id=draft.draft_id)

    async def confirm_order(self, draft_id: str) -> PaperOrderResult:
        async with self._lock:
            draft = self._drafts.get(draft_id)
            now = self._current_time()
            if draft is None or draft.expires_at <= now:
                raise PaperTradingUIUnavailableError()
            if draft.cash_effect_paise is None or draft.charge_paise is None:
                raise PaperTradingUIUnavailableError()

            key = (draft.exchange, draft.symbol_token)
            holding = self._holdings.get(key)
            next_cash_paise = self._cash_paise + draft.cash_effect_paise
            if next_cash_paise < 0:
                raise PaperTradingUIUnavailableError()
            if draft.side == "buy":
                required_cash = -draft.cash_effect_paise
                if required_cash < 0 or self._cash_paise < required_cash:
                    raise PaperTradingUIUnavailableError()
                if holding is None:
                    self._holdings[key] = _Holding(
                        quantity=draft.quantity,
                        cost_basis_paise=draft.notional_paise + draft.charge_paise,
                    )
                else:
                    holding.quantity += draft.quantity
                    holding.cost_basis_paise += (
                        draft.notional_paise + draft.charge_paise
                    )
            else:
                if holding is None or holding.quantity < draft.quantity:
                    raise PaperTradingUIUnavailableError()
                cost_sold_paise = (
                    holding.cost_basis_paise * draft.quantity // holding.quantity
                )
                holding.quantity -= draft.quantity
                holding.cost_basis_paise -= cost_sold_paise
                if holding.quantity == 0:
                    del self._holdings[key]

            self._cash_paise = next_cash_paise
            del self._drafts[draft_id]
            self._applied_draft_ids.add(draft_id)
            return PaperOrderResult(
                draft_id=draft.draft_id,
                side=draft.side,
                trading_symbol=draft.trading_symbol,
                quantity=draft.quantity,
                fill_price_paise=draft.price_paise,
                simulated_at=now,
                cash_paise=self._cash_paise,
            )

    async def get_portfolio_summary(self) -> PaperPortfolioSummary:
        async with self._lock:
            holdings_cost_basis_paise = sum(
                holding.cost_basis_paise for holding in self._holdings.values()
            )
            return PaperPortfolioSummary(
                cash_paise=self._cash_paise,
                holdings_cost_basis_paise=holdings_cost_basis_paise,
                cash_plus_cost_basis_paise=(
                    self._cash_paise + holdings_cost_basis_paise
                ),
            )

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise PaperTradingUIUnavailableError()
        return value.astimezone(UTC)
