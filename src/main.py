"""Scheduler entrypoint. See AGENTS.md §12 for the job table.

Jobs: discover_markets (10m), discover_fixtures (30m), link_events,
poll_kalshi_books (15-30s per market or WS), poll_pinnacle,
strategy_tick (15s), pre_start_cancel (10s), reconcile (60s),
settle (15m), maintenance_guard (no orders 3-5 AM ET).
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("scheduler not implemented yet")


if __name__ == "__main__":
    main()
