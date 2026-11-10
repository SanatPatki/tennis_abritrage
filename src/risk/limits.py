"""Pre-trade risk checks. See AGENTS.md §9.

Checks before every place/amend:
- exposure_after_order(match) <= MAX_EXPOSURE_PER_MATCH
- exposure_today <= MAX_EXPOSURE_PER_DAY
- open_exposure_total <= MAX_TOTAL_EXPOSURE
- open_orders_count <= MAX_OPEN_ORDERS
- daily_realized_pnl >= -MAX_DAILY_LOSS
- no more than one side (YES or NO) of the same match at once

Exposure = max loss = price * contracts for buys (+ fees).
Any breach -> kill switch.
"""

from __future__ import annotations


class RiskLimits:
    """TODO: implement checks against DB state + config limits."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
