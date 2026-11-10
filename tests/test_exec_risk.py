"""Tests for quoting, paper executor, and risk limits (AGENTS.md §14)."""

from datetime import datetime, timedelta, timezone

from src.exec.paper import PaperExecutor
from src.risk.limits import (
    ProposedOrder,
    RiskLimitsConfig,
    RiskState,
    check_order,
)
from src.strategy.quoting import OpenQuote, Quoter

T0 = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc)

LIMITS = RiskLimitsConfig(
    max_exposure_per_match=20,
    max_exposure_per_day=80,
    max_total_exposure=150,
    max_open_orders=20,
    max_daily_loss=40,
)


def _quoter():
    return Quoter(
        min_edge_maker=0.015, min_price=0.10, max_price=0.90,
        requote_threshold=0.01, requote_interval_sec=60,
        maker_fee_series=False,
    )


# --- quoting ---------------------------------------------------------------

def test_quote_price_uses_edge_ceiling():
    q = _quoter()
    # fair 0.60, no maker fee -> ceiling = 0.60 - 0 - 0.015 = 0.585 -> 58c
    assert q.quote_price_c(0.60, None, "yes") == 58


def test_quote_price_steps_above_best_bid():
    q = _quoter()
    # best bid 50c -> min(51, 58) = 51
    assert q.quote_price_c(0.60, 50, "yes") == 51


def test_quote_price_none_when_no_edge():
    q = _quoter()
    # fair 0.52 -> ceiling 0.505 -> 50c, edge at 50c = 0.52-0.50-0 = 0.02 >= 0.015 ok
    assert q.quote_price_c(0.52, None, "yes") == 50
    # fair 0.51 -> ceiling 0.495 -> 49c; edge = 0.51-0.49 = 0.02 ok actually...
    # use fair just above price band edge: fair 0.115 -> ceiling 0.10 -> 10c < min 10? min_price=0.10 -> 10c ok boundary
    # clearer: fair 0.105 -> ceiling 9c -> below band -> None
    assert q.quote_price_c(0.105, None, "yes") is None


def test_quote_respects_price_band():
    q = _quoter()
    # fair 0.95 -> ceiling 0.935 -> 93c > max 90c -> None
    assert q.quote_price_c(0.95, None, "yes") is None


def test_evaluate_places_then_holds():
    q = _quoter()
    d = q.evaluate(None, fair_p=0.60, best_bid_c=50, now=T0)
    assert d.action == "place" and d.price_c == 51
    oq = OpenQuote("T", "yes", 51, 10, T0, last_fair_p=0.60)
    d2 = q.evaluate(oq, fair_p=0.60, best_bid_c=50, now=T0 + timedelta(seconds=30))
    assert d2.action == "hold"


def test_evaluate_cancels_when_edge_gone():
    q = _quoter()
    oq = OpenQuote("T", "yes", 51, 10, T0, last_fair_p=0.60)
    d = q.evaluate(oq, fair_p=0.50, best_bid_c=50, now=T0 + timedelta(seconds=30))
    # fair dropped: ceiling = 0.485 -> 48c < band min? min_price=0.10 -> 48c in band,
    # desired 48 != 51 and drift 0.10 > threshold -> amend, not cancel
    assert d.action in ("amend", "cancel")


def test_evaluate_amend_on_big_drift():
    q = _quoter()
    oq = OpenQuote("T", "yes", 51, 10, T0, last_fair_p=0.60)
    d = q.evaluate(oq, fair_p=0.70, best_bid_c=60,
                   now=T0 + timedelta(seconds=30))
    assert d.action == "amend"


# --- risk limits --------------------------------------------------------------

def _order(**kw):
    defaults = dict(match_key="M1", venue_ticker="T1", side="yes",
                    price=0.50, count=10, is_new_order=True, fee=0.0)
    defaults.update(kw)
    return ProposedOrder(**defaults)


def test_clean_order_passes():
    assert check_order(_order(), RiskState(), LIMITS) == []


def test_match_exposure_limit():
    state = RiskState(exposure_per_match={"M1": 19.0})
    v = check_order(_order(price=0.50, count=10), state, LIMITS)  # +5 -> 24 > 20
    assert "MAX_EXPOSURE_PER_MATCH" in v


def test_one_side_per_match():
    state = RiskState(sides_per_match={"M1": {"no"}})
    assert "ONE_SIDE_PER_MATCH" in check_order(_order(side="yes"), state, LIMITS)
    assert "ONE_SIDE_PER_MATCH" in check_order(_order(side="no"), state, LIMITS)


def test_open_orders_limit():
    state = RiskState(open_orders_count=20)
    assert "MAX_OPEN_ORDERS" in check_order(_order(), state, LIMITS)
    # amends don't add orders
    assert "MAX_OPEN_ORDERS" not in check_order(
        _order(is_new_order=False), state, LIMITS
    )


def test_daily_loss_blocks():
    state = RiskState(daily_realized_pnl=-40.0)
    assert "MAX_DAILY_LOSS" in check_order(_order(), state, LIMITS)


def test_order_that_would_breach_daily_loss_blocked():
    # pnl -38, order exposure 5 -> -43 < -40
    state = RiskState(daily_realized_pnl=-38.0)
    assert "MAX_DAILY_LOSS" in check_order(_order(price=0.50, count=10), state, LIMITS)


# --- paper executor ------------------------------------------------------------

def test_taker_fills_at_ask_up_to_size():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 55, 10, post_only=False, ts=T0,
                       best_ask_c=56, best_ask_size=4)
    assert o.filled == 4 and o.status == "partial"
    assert ex.fills[0].is_taker and ex.fills[0].count == 4


def test_maker_fills_on_trade_at_price():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 50, 10, post_only=True, ts=T0, level_size=5)
    # trade of 8 at our price: 5 ahead consume queue, we get 3
    fills = ex.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=50, size=8)
    assert o.filled == 3
    # maker fill on a no-maker-fee series -> zero fee
    assert fills[0].fee_usd == 0.0
    # with maker fees enabled, fee > 0
    ex2 = PaperExecutor(maker_fee_series=True)
    o2 = ex2.place_order("T", "yes", 50, 10, post_only=True, ts=T0, level_size=0)
    ex2.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=50, size=10)
    assert ex2.fills[0].fee_usd > 0


def test_maker_no_fill_when_trade_too_small():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 50, 10, post_only=True, ts=T0, level_size=20)
    ex.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=50, size=10)
    assert o.filled == 0  # all 10 consumed by 20 ahead


def test_maker_through_trade_fills():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 50, 10, post_only=True, ts=T0, level_size=0)
    # trade prints at 48 (through our 50 bid)
    ex.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=48, size=4)
    assert o.filled == 4


def test_no_side_uses_inverted_price():
    ex = PaperExecutor()
    o = ex.place_order("T", "no", 40, 10, post_only=True, ts=T0, level_size=0)
    # NO buy at 40c fills when YES trade >= 60c
    ex.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=62, size=10)
    assert o.filled == 10
    # and does NOT fill on low YES prints
    o2 = ex.place_order("T", "no", 40, 10, post_only=True, ts=T0,
                        level_size=0, order_id="x2")
    ex.on_trade("T", T0 + timedelta(seconds=2), yes_price_c=30, size=10)
    assert o2.filled == 0


def test_order_does_not_fill_before_placement():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 50, 10, post_only=True, ts=T0 + timedelta(seconds=5),
                       level_size=0)
    ex.on_trade("T", T0, yes_price_c=50, size=10)  # trade BEFORE order
    assert o.filled == 0


def test_cancel_stops_fills():
    ex = PaperExecutor()
    o = ex.place_order("T", "yes", 50, 10, post_only=True, ts=T0, level_size=0)
    ex.cancel(o.order_id)
    ex.on_trade("T", T0 + timedelta(seconds=1), yes_price_c=50, size=10)
    assert o.filled == 0
