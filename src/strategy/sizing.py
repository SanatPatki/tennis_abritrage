"""Fractional Kelly sizing with caps. See AGENTS.md §6.3."""

from __future__ import annotations

import math


def kelly_contracts(
    fair_p: float,
    price: float,
    bankroll_usd: float,
    kelly_fraction: float,
    max_contracts: int,
) -> int:
    """Contracts = floor(KELLY_FRACTION * kelly_f * bankroll / price), capped.

    kelly_f = (fair_p - price) / (1 - price) for buying YES at `price`.
    Returns 0 if contracts < 1 (caller should skip).
    """
    if price <= 0 or price >= 1 or fair_p <= price:
        return 0
    kelly_f = (fair_p - price) / (1 - price)
    stake = kelly_fraction * kelly_f * bankroll_usd
    contracts = math.floor(stake / price + 1e-9)  # epsilon for float dust
    return min(contracts, max_contracts)
