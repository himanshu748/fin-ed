from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import fined.paper_trading as paper_trading
from fined.paper_trading import PaperOrderDraft, PaperTradingUIUnavailableError

CallPaperTradingBridge = getattr(paper_trading, "CallPaperTradingBridge", None)


NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)


def _draft(
    draft_id: str,
    *,
    side: str = "buy",
    quantity: int = 2,
    price_paise: int = 250_050,
    charge_paise: int = 123,
) -> PaperOrderDraft:
    notional_paise = quantity * price_paise
    cash_effect_paise = (
        -(notional_paise + charge_paise)
        if side == "buy"
        else notional_paise - charge_paise
    )
    return PaperOrderDraft(
        draft_id=draft_id,
        side=side,  # type: ignore[arg-type]
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        quantity=quantity,
        price_paise=price_paise,
        quote_provider="Angel One SmartAPI",
        quote_time=NOW,
        expires_at=NOW + timedelta(seconds=30),
        notional_paise=notional_paise,
        charge_paise=charge_paise,
        cash_effect_paise=cash_effect_paise,
        charge_status="estimated",
    )


@pytest.mark.asyncio
async def test_call_portfolio_starts_with_one_lakh_and_applies_one_confirmed_buy() -> (
    None
):
    # Catches an outbound paper fill using real money or changing cash before confirm.
    assert CallPaperTradingBridge is not None
    bridge = CallPaperTradingBridge(now=lambda: NOW + timedelta(seconds=1))
    draft = _draft("buy-1")

    acknowledgement = await bridge.prepare_order(draft)
    before = await bridge.get_portfolio_summary()
    result = await bridge.confirm_order(draft.draft_id)
    after = await bridge.get_portfolio_summary()

    assert acknowledgement.prepared is True
    assert before.cash_paise == 10_000_000
    assert result.cash_paise == 9_499_777
    assert after.cash_paise == 9_499_777
    assert after.holdings_cost_basis_paise == 500_223
    assert after.cash_plus_cost_basis_paise == 10_000_000

    with pytest.raises(PaperTradingUIUnavailableError):
        await bridge.confirm_order(draft.draft_id)


@pytest.mark.asyncio
async def test_call_portfolio_rejects_naked_sell_then_sells_an_owned_quantity() -> None:
    # Catches phone paper trading permitting short sales or ignoring holdings.
    assert CallPaperTradingBridge is not None
    bridge = CallPaperTradingBridge(now=lambda: NOW + timedelta(seconds=1))
    naked_sell = _draft("sell-0", side="sell", quantity=1, price_paise=260_000)
    await bridge.prepare_order(naked_sell)

    with pytest.raises(PaperTradingUIUnavailableError):
        await bridge.confirm_order(naked_sell.draft_id)

    buy = _draft("buy-1")
    await bridge.prepare_order(buy)
    await bridge.confirm_order(buy.draft_id)
    sell = _draft(
        "sell-1", side="sell", quantity=1, price_paise=260_000, charge_paise=200
    )
    await bridge.prepare_order(sell)
    result = await bridge.confirm_order(sell.draft_id)
    summary = await bridge.get_portfolio_summary()

    assert result.cash_paise == 9_759_577
    assert summary.holdings_cost_basis_paise == 250_112
    assert summary.cash_plus_cost_basis_paise == 10_009_689


@pytest.mark.asyncio
async def test_call_portfolio_rejects_expired_or_unpriced_drafts() -> None:
    # Catches stale or charge-unknown phone drafts being applied to virtual cash.
    assert CallPaperTradingBridge is not None
    expired_bridge = CallPaperTradingBridge(now=lambda: NOW + timedelta(seconds=31))
    expired = _draft("expired")
    with pytest.raises(PaperTradingUIUnavailableError):
        await expired_bridge.prepare_order(expired)

    unpriced_bridge = CallPaperTradingBridge(now=lambda: NOW + timedelta(seconds=1))
    unpriced = PaperOrderDraft(
        draft_id="unpriced",
        side="buy",
        exchange="NSE",
        symbol_token="2885",
        trading_symbol="RELIANCE-EQ",
        quantity=1,
        price_paise=250_050,
        quote_provider="Angel One SmartAPI",
        quote_time=NOW,
        expires_at=NOW + timedelta(seconds=30),
        notional_paise=250_050,
        charge_paise=None,
        cash_effect_paise=None,
        charge_status="unavailable",
    )
    with pytest.raises(PaperTradingUIUnavailableError):
        await unpriced_bridge.prepare_order(unpriced)


@pytest.mark.asyncio
async def test_failed_sell_cannot_partially_mutate_call_portfolio() -> None:
    # Catches a fee-heavy sell making cash negative after holdings were removed.
    bridge = CallPaperTradingBridge(now=lambda: NOW + timedelta(seconds=1))
    buy = _draft(
        "buy-all",
        quantity=1,
        price_paise=9_999_000,
        charge_paise=1_000,
    )
    await bridge.prepare_order(buy)
    await bridge.confirm_order(buy.draft_id)
    sell = _draft(
        "sell-loss",
        side="sell",
        quantity=1,
        price_paise=1,
        charge_paise=2,
    )
    await bridge.prepare_order(sell)

    with pytest.raises(PaperTradingUIUnavailableError):
        await bridge.confirm_order(sell.draft_id)

    summary = await bridge.get_portfolio_summary()
    assert summary.cash_paise == 0
    assert summary.holdings_cost_basis_paise == 10_000_000
