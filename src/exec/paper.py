"""Paper executor — simulated fills. See AGENTS.md §10.

- Taker: fill at current best opposite price up to displayed size; remainder unfilled.
- Maker: filled only when a logged trade prints at/through our price AFTER order
  time, up to trade size minus size ahead of us in queue (assume last in queue).
- Fees via kalshi_fee (§6.2). Flag if maker fill rate > 50%.
"""

from __future__ import annotations


class PaperExecutor:
    """TODO: implement simulated fills against book_snapshots/trades."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
