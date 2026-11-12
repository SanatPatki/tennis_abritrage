"""Read-only dashboard API. See docs/dashboard.md.

Binds to localhost only. Uses a SELECT-only Postgres role (bot_ro) via
DATABASE_URL_RO (falls back to DATABASE_URL for dev). Never writes.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

from ..config import Settings
from ..main import in_maintenance_window
from ..risk.killswitch import LOCK_PATH, is_locked

STATIC = Path(__file__).parent / "static"


def _db_url() -> str:
    return os.environ.get("DATABASE_URL_RO") or os.environ.get("DATABASE_URL") or ""


@contextmanager
def _ro():
    url = _db_url()
    if not url:
        yield None
        return
    conn = psycopg.connect(url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


app = FastAPI(title="tennis-bot dashboard", docs_url=None, redoc_url=None)


@app.get("/api/status")
def status() -> dict:
    s = Settings.load()
    return {
        "mode": s.mode,
        "live_allowed": s.live_allowed,
        "kalshi_env": s.kalshi_env,
        "maintenance_window": in_maintenance_window(),
        "kill_switch_locked": is_locked(),
        "kill_lock_path": LOCK_PATH,
        "now_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/risk")
def risk() -> dict:
    with _ro() as conn:
        if conn is None:
            return {"error": "DATABASE_URL not set"}
        from ..db.repo import get_risk_state
        st = get_risk_state(conn)
        return {
            "exposure_per_match": st.exposure_per_match,
            "exposure_today": st.exposure_today,
            "open_exposure_total": st.open_exposure_total,
            "open_orders_count": st.open_orders_count,
            "daily_realized_pnl": st.daily_realized_pnl,
            "sides_per_match": {k: sorted(v) for k, v in st.sides_per_match.items()},
        }


@app.get("/api/orders")
def orders(status: str = "open") -> dict:
    with _ro() as conn:
        if conn is None:
            return {"error": "DATABASE_URL not set"}
        rows = conn.execute(
            """SELECT client_order_id, venue_ticker, side, action, price_c,
                      count, post_only, status, mode, created_at, updated_at
               FROM orders WHERE status = ANY(%s)
               ORDER BY created_at DESC LIMIT 100""",
            (["open", "partial"] if status == "open" else [status, "open", "partial", "filled", "cancelled"],),
        ).fetchall()
        return {"orders": [dict(r) for r in rows]}


@app.get("/api/decisions")
def decisions(limit: int = 50) -> dict:
    with _ro() as conn:
        if conn is None:
            return {"error": "DATABASE_URL not set"}
        rows = conn.execute(
            """SELECT ts, venue_ticker, side, fair_p, price_c, fee_c, edge,
                      action, reason, mode
               FROM decisions ORDER BY ts DESC LIMIT %s""",
            (min(limit, 500),),
        ).fetchall()
        return {"decisions": [dict(r) for r in rows]}


@app.get("/api/matches")
def matches() -> dict:
    """Venue markets joined to latest book + odds snapshots and match links."""
    with _ro() as conn:
        if conn is None:
            return {"error": "DATABASE_URL not set"}
        rows = conn.execute(
            """SELECT vm.venue, vm.venue_ticker, vm.event_ticker, vm.close_time,
                      m.tournament, m.scheduled_start, m.status AS match_status,
                      p.canonical AS yes_player,
                      (SELECT yes_bid_c FROM book_snapshots b
                        WHERE b.venue_ticker = vm.venue_ticker
                        ORDER BY ts DESC LIMIT 1) AS yes_bid_c,
                      (SELECT yes_ask_c FROM book_snapshots b
                        WHERE b.venue_ticker = vm.venue_ticker
                        ORDER BY ts DESC LIMIT 1) AS yes_ask_c,
                      (SELECT fair_p1 FROM odds_snapshots o
                        WHERE o.match_id = vm.match_id AND o.book = 'pinnacle'
                        ORDER BY ts DESC LIMIT 1) AS fair_p1,
                      (SELECT max(confidence) FROM match_links ml
                        WHERE ml.match_id = vm.match_id) AS link_confidence
               FROM venue_markets vm
               LEFT JOIN matches m ON m.match_id = vm.match_id
               LEFT JOIN players p ON p.player_id = vm.yes_player_id
               ORDER BY m.scheduled_start NULLS LAST
               LIMIT 200"""
        ).fetchall()
        return {"matches": [dict(r) for r in rows]}


@app.get("/api/fills")
def fills(limit: int = 50) -> dict:
    with _ro() as conn:
        if conn is None:
            return {"error": "DATABASE_URL not set"}
        rows = conn.execute(
            """SELECT f.fill_id, f.ts, f.price_c, f.count, f.fee_cost_c,
                      f.is_taker, f.mode, o.venue_ticker, o.side
               FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id
               ORDER BY f.ts DESC LIMIT %s""",
            (min(limit, 500),),
        ).fetchall()
        return {"fills": [dict(r) for r in rows]}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def main() -> None:
    import uvicorn
    uvicorn.run("src.dashboard.app:app", host="127.0.0.1", port=8080, reload=False)


if __name__ == "__main__":
    main()
