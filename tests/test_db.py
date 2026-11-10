"""DB integration test — requires local Postgres (DATABASE_URL).

Skipped automatically when DATABASE_URL is unset or unreachable.
"""

import os
from datetime import datetime, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

from src.db import repo
from src.db.connection import connect, migrate
from src.risk.limits import ProposedOrder, check_order
from src.db.repo import get_risk_state
from src.risk.limits import RiskLimitsConfig

LIMITS = RiskLimitsConfig(20, 80, 150, 20, 40)


def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    try:
        with connect(url) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="no DATABASE_URL / db down")


@pytest.fixture()
def conn():
    migrate(os.environ["DATABASE_URL"])
    with connect(os.environ["DATABASE_URL"]) as c:
        # clean slate for test tables
        for t in ("fills", "orders", "decisions", "book_snapshots",
                  "odds_snapshots", "match_links", "venue_markets",
                  "matches", "players"):
            c.execute(f"DELETE FROM {t}")
        yield c


def test_migrate_and_roundtrip(conn):
    pid = repo.upsert_player(conn, "Jannik Sinner", "ATP", sackmann_id=123)
    mid = repo.insert_match(conn, "ATP", scheduled_start=datetime(2026, 11, 15, tzinfo=timezone.utc),
                            tournament="ATP Finals", p1_id=pid, p2_id=pid)
    repo.upsert_venue_market(conn, "kalshi", "KXATPMATCH-T", event_ticker="KXATPMATCH-T",
                             match_id=mid, yes_player_id=pid, rulebook="TENNISSETWINNER")
    repo.insert_match_link(conn, mid, "fx1", 0.97, "fuzzy-v1")
    ts = datetime(2026, 11, 14, tzinfo=timezone.utc)
    repo.insert_book_snapshot(conn, "kalshi", "KXATPMATCH-T", ts,
                              yes_bid_c=48, yes_ask_c=52, yes_bid_sz=100, yes_ask_sz=50)
    repo.insert_odds_snapshot(conn, ts, mid, "pinnacle", 1.9, 2.0, 0.51, 0.026, "multiplicative")
    repo.insert_decision(conn, ts, "place", "QUOTE_OK", "paper",
                         match_id=mid, venue_ticker="KXATPMATCH-T", side="yes",
                         fair_p=0.55, price_c=50, fee_c=1, edge=0.04)
    repo.upsert_order(conn, "tb-1", "KXATPMATCH-T", "yes", "buy", 50, 10, True, "open", "paper")
    repo.insert_fill(conn, "f1", "tb-1", ts, 50, 5, 1, False, "paper")

    n = conn.execute("SELECT count(*) c FROM orders").fetchone()["c"]
    assert n == 1
    # upsert is idempotent
    repo.upsert_order(conn, "tb-1", "KXATPMATCH-T", "yes", "buy", 50, 10, True, "filled", "paper")
    assert conn.execute("SELECT count(*) c FROM orders").fetchone()["c"] == 1


def test_risk_state_from_db(conn):
    repo.upsert_venue_market(conn, "kalshi", "KX-T", event_ticker="EVT-1")
    repo.upsert_order(conn, "o1", "KX-T", "yes", "buy", 50, 20, True, "open", "paper")
    state = get_risk_state(conn)
    assert state.open_orders_count == 1
    assert state.exposure_per_match["EVT-1"] == pytest.approx(10.0)
    v = check_order(
        ProposedOrder(match_key="EVT-1", venue_ticker="KX-T", side="yes",
                      price=0.50, count=30),
        state, LIMITS,
    )
    assert "MAX_EXPOSURE_PER_MATCH" in v
