"""Pre-trade risk checks. See AGENTS.md §9.

Checks before every place/amend:
- exposure_after_order(match) <= MAX_EXPOSURE_PER_MATCH
- exposure_today <= MAX_EXPOSURE_PER_DAY
- open_exposure_total <= MAX_TOTAL_EXPOSURE
- open_orders_count <= MAX_OPEN_ORDERS
- daily_realized_pnl >= -MAX_DAILY_LOSS
- no more than one side (YES or NO) of the same match at once

Exposure = max loss = price * contracts for buys (+ fees).
Any breach -> kill switch (see killswitch.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskLimitsConfig:
    max_exposure_per_match: float
    max_exposure_per_day: float
    max_total_exposure: float
    max_open_orders: int
    max_daily_loss: float


@dataclass
class RiskState:
    """Snapshot of current risk state, supplied by the caller (DB/venue)."""

    exposure_per_match: dict[str, float] = field(default_factory=dict)  # match key -> $
    exposure_today: float = 0.0
    open_exposure_total: float = 0.0
    open_orders_count: int = 0
    daily_realized_pnl: float = 0.0
    # match key -> set of sides already held/quoted ('yes' | 'no')
    sides_per_match: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class ProposedOrder:
    match_key: str          # stable per-match key (e.g. event_ticker)
    venue_ticker: str
    side: str               # 'yes' | 'no'
    price: float            # dollars
    count: int
    is_new_order: bool = True   # False for amends (no count change against open_orders)
    fee: float = 0.0            # estimated fee in dollars

    @property
    def exposure(self) -> float:
        return self.price * self.count + self.fee


def check_order(
    order: ProposedOrder,
    state: RiskState,
    limits: RiskLimitsConfig,
) -> list[str]:
    """Return list of violated rule codes; empty list means the order may proceed."""
    violations: list[str] = []

    # one side per match: can't hold/quote YES and NO on the same match
    existing_sides = state.sides_per_match.get(order.match_key, set())
    other_side = "no" if order.side == "yes" else "yes"
    if order.side in existing_sides or other_side in existing_sides:
        violations.append("ONE_SIDE_PER_MATCH")

    match_exposure_after = state.exposure_per_match.get(order.match_key, 0.0) + order.exposure
    if match_exposure_after > limits.max_exposure_per_match:
        violations.append("MAX_EXPOSURE_PER_MATCH")

    if state.exposure_today + order.exposure > limits.max_exposure_per_day:
        violations.append("MAX_EXPOSURE_PER_DAY")

    open_exposure_after = state.open_exposure_total + (
        order.exposure if order.is_new_order else 0.0
    )
    if open_exposure_after > limits.max_total_exposure:
        violations.append("MAX_TOTAL_EXPOSURE")

    if order.is_new_order and state.open_orders_count + 1 > limits.max_open_orders:
        violations.append("MAX_OPEN_ORDERS")

    # daily loss limit: realized P&L already breached, or this order could add
    # exposure that, if fully lost, breaches it
    if state.daily_realized_pnl <= -limits.max_daily_loss:
        violations.append("MAX_DAILY_LOSS")
    elif state.daily_realized_pnl - order.exposure < -limits.max_daily_loss:
        violations.append("MAX_DAILY_LOSS")

    return violations
