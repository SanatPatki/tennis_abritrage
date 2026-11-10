"""Maker price selection and requote logic. See AGENTS.md §2.

Maker quote: post-only bid at min(best_bid + 1c, fair_p - fee - MIN_EDGE_MAKER).
Requote when fair value moves > REQUOTE_THRESHOLD or every REQUOTE_INTERVAL_SEC.
Use Kalshi `amend` instead of cancel+new where possible.
"""

from __future__ import annotations


class Quoter:
    """TODO: implement quote price selection + requote state machine."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
