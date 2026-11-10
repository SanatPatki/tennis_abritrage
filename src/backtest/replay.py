"""Stage B replay: replay book_snapshots + odds_snapshots chronologically
through strategy/ with the paper executor. See AGENTS.md §11.

Report: trades, fill rate, mean edge at entry, mean CLV vs Pinnacle close,
P&L after fees, max drawdown, P&L by price bucket / tour / hours-to-start.
"""

from __future__ import annotations


def run_replay(*args, **kwargs):
    raise NotImplementedError
