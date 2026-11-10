"""Edge computation. See AGENTS.md §2."""

from __future__ import annotations

from dataclasses import dataclass

from ..clients.kalshi import kalshi_fee


@dataclass
class Signal:
    side: str            # 'yes' | 'no'
    fair_p: float
    price: float         # dollars paid per contract
    fee: float           # dollars per contract (order-total rounding applied at sizing)
    edge: float          # fair_p - price - fee  (probability points)


def compute_edges(
    fair_p_yes: float,
    yes_price: float,
    no_price: float,
    contracts: int,
    maker_fee_series: bool,
) -> tuple[Signal, Signal]:
    """Return (yes_signal, no_signal).

    NO side is equivalent to selling YES: edge_no = (1 - fair_p) - no_price - fee.
    """
    fee_yes = kalshi_fee(yes_price, contracts, maker=True, maker_fee_series=maker_fee_series)
    fee_no = kalshi_fee(no_price, contracts, maker=True, maker_fee_series=maker_fee_series)
    yes_sig = Signal(
        side="yes",
        fair_p=fair_p_yes,
        price=yes_price,
        fee=fee_yes,
        edge=fair_p_yes - yes_price - fee_yes,
    )
    no_sig = Signal(
        side="no",
        fair_p=1.0 - fair_p_yes,
        price=no_price,
        fee=fee_no,
        edge=(1.0 - fair_p_yes) - no_price - fee_no,
    )
    return yes_sig, no_sig
