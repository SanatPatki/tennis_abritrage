"""Reconciliation: positions + resting orders vs DB every RECONCILE_INTERVAL_SEC.
Any mismatch -> kill switch. See AGENTS.md §9, §12.
"""

from __future__ import annotations


class Reconciler:
    """TODO: compare GET /portfolio/positions + resting orders to DB."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
