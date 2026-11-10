"""Scheduler entrypoint. See AGENTS.md §12 for the job table.

Jobs: discover_markets (10m), discover_fixtures (30m), link_events,
poll_kalshi_books (15-30s per market or WS), poll_pinnacle,
strategy_tick (15s), pre_start_cancel (10s), reconcile (60s),
settle (15m), maintenance_guard (no orders 3-5 AM ET).

Most jobs depend on API clients that are not implemented yet; they log and
skip rather than crash. MODE=paper is the default and live trading remains
env-gated in exec/live.py.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from .db.connection import connect, migrate

log = logging.getLogger("tennis_bot")

ET = ZoneInfo("America/New_York")
MAINTENANCE_START = time(3, 0)
MAINTENANCE_END = time(5, 0)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def in_maintenance_window(now: datetime | None = None) -> bool:
    """True during Kalshi weekly maintenance, 3-5 AM ET. See AGENTS.md §4.1."""
    now = now or datetime.now(ET)
    t = now.astimezone(ET).time()
    return MAINTENANCE_START <= t < MAINTENANCE_END


# -- job callables -----------------------------------------------------------
# Each takes no args; heavy lifting lives in the modules they call.
# Until the API clients exist they log and return.

def _skip(name: str, reason: str) -> None:
    log.info("job %s skipped: %s", name, reason)


def job_discover_markets() -> None:
    _skip("discover_markets", "Kalshi client endpoints not implemented")


def job_discover_fixtures() -> None:
    _skip("discover_fixtures", "odds provider client not implemented")


def job_link_events() -> None:
    _skip("link_events", "needs discover_markets + discover_fixtures output")


def job_poll_kalshi_books() -> None:
    _skip("poll_kalshi_books", "Kalshi client endpoints not implemented")


def job_poll_pinnacle() -> None:
    _skip("poll_pinnacle", "odds provider client not implemented")


def job_strategy_tick() -> None:
    if in_maintenance_window():
        log.info("strategy_tick: maintenance window, no orders")
        return
    _skip("strategy_tick", "needs book/odds snapshots + match links")


def job_pre_start_cancel() -> None:
    _skip("pre_start_cancel", "needs resting orders from DB/venue")


def job_reconcile() -> None:
    _skip("reconcile", "needs venue positions endpoint")


def job_settle() -> None:
    _skip("settle", "needs market settlement data")


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job_discover_markets, "interval", minutes=10, id="discover_markets")
    sched.add_job(job_discover_fixtures, "interval", minutes=30, id="discover_fixtures")
    sched.add_job(job_link_events, "interval", minutes=10, id="link_events")
    sched.add_job(job_poll_kalshi_books, "interval", seconds=30, id="poll_kalshi_books")
    sched.add_job(job_poll_pinnacle, "interval", minutes=5, id="poll_pinnacle")
    sched.add_job(job_strategy_tick, "interval", seconds=15, id="strategy_tick")
    sched.add_job(job_pre_start_cancel, "interval", seconds=10, id="pre_start_cancel")
    sched.add_job(job_reconcile, "interval", seconds=60, id="reconcile")
    sched.add_job(job_settle, "interval", minutes=15, id="settle")
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()
    cfg = load_config()
    mode = cfg.get("MODE", "paper")
    log.info("starting scheduler MODE=%s KALSHI_ENV=%s", mode, cfg.get("KALSHI_ENV"))

    with connect() as conn:
        applied = migrate()
        if applied:
            log.info("applied migrations: %s", applied)

    sched = build_scheduler()
    sched.start()
    log.info("scheduler running — Ctrl-C to stop")
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        sched.shutdown()


if __name__ == "__main__":
    main()
