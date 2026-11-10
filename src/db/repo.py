"""Typed repository helpers for the AGENTS.md §8 schema.

All functions take an open psycopg connection (dict_row). Prices are integer
cents in venue tables; probabilities REAL in [0,1]. Timestamps UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg


# -- reference data ---------------------------------------------------------

def upsert_player(
    conn: psycopg.Connection, canonical: str, tour: str,
    sackmann_id: int | None = None,
) -> int:
    row = conn.execute(
        """INSERT INTO players (canonical, sackmann_id, tour)
           VALUES (%s, %s, %s)
           ON CONFLICT (canonical) DO UPDATE SET sackmann_id = EXCLUDED.sackmann_id
           RETURNING player_id""",
        (canonical, sackmann_id, tour),
    ).fetchone()
    return row["player_id"]


def insert_match(
    conn: psycopg.Connection,
    tour: str,
    scheduled_start: datetime | None = None,
    tournament: str | None = None,
    surface: str | None = None,
    round_: str | None = None,
    p1_id: int | None = None,
    p2_id: int | None = None,
    status: str = "scheduled",
) -> int:
    row = conn.execute(
        """INSERT INTO matches (tour, tournament, surface, round,
                                p1_id, p2_id, scheduled_start, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING match_id""",
        (tour, tournament, surface, round_, p1_id, p2_id, scheduled_start, status),
    ).fetchone()
    return row["match_id"]


def upsert_venue_market(
    conn: psycopg.Connection,
    venue: str,
    venue_ticker: str,
    event_ticker: str | None = None,
    match_id: int | None = None,
    yes_player_id: int | None = None,
    rulebook: str | None = None,
    close_time: datetime | None = None,
) -> None:
    conn.execute(
        """INSERT INTO venue_markets
             (venue, venue_ticker, event_ticker, match_id, yes_player_id, rulebook, close_time)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (venue, venue_ticker) DO UPDATE SET
             event_ticker = EXCLUDED.event_ticker,
             match_id = EXCLUDED.match_id,
             yes_player_id = EXCLUDED.yes_player_id,
             rulebook = EXCLUDED.rulebook,
             close_time = EXCLUDED.close_time""",
        (venue, venue_ticker, event_ticker, match_id, yes_player_id, rulebook, close_time),
    )


def insert_match_link(
    conn: psycopg.Connection,
    match_id: int,
    odds_fixture_id: str,
    confidence: float,
    method: str,
) -> None:
    conn.execute(
        """INSERT INTO match_links (match_id, odds_fixture_id, confidence, method)
           VALUES (%s,%s,%s,%s)""",
        (match_id, odds_fixture_id, confidence, method),
    )


# -- snapshots (append-only) -------------------------------------------------

def insert_book_snapshot(
    conn: psycopg.Connection,
    venue: str,
    venue_ticker: str,
    ts: datetime,
    yes_bid_c: int | None = None,
    yes_ask_c: int | None = None,
    yes_bid_sz: int | None = None,
    yes_ask_sz: int | None = None,
    last_c: int | None = None,
    volume: int | None = None,
    open_interest: int | None = None,
) -> None:
    conn.execute(
        """INSERT INTO book_snapshots
             (ts, venue, venue_ticker, yes_bid_c, yes_ask_c, yes_bid_sz, yes_ask_sz,
              last_c, volume, open_interest)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (ts, venue, venue_ticker, yes_bid_c, yes_ask_c, yes_bid_sz, yes_ask_sz,
         last_c, volume, open_interest),
    )


def insert_odds_snapshot(
    conn: psycopg.Connection,
    ts: datetime,
    match_id: int,
    book: str,
    odds_p1: float | None = None,
    odds_p2: float | None = None,
    fair_p1: float | None = None,
    overround: float | None = None,
    devig_method: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO odds_snapshots
             (ts, match_id, book, odds_p1, odds_p2, fair_p1, overround, devig_method)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (ts, match_id, book, odds_p1, odds_p2, fair_p1, overround, devig_method),
    )


# -- decisions / orders / fills ----------------------------------------------

def insert_decision(
    conn: psycopg.Connection,
    ts: datetime,
    action: str,
    reason: str,
    mode: str,
    match_id: int | None = None,
    venue_ticker: str | None = None,
    side: str | None = None,
    fair_p: float | None = None,
    price_c: int | None = None,
    fee_c: int | None = None,
    edge: float | None = None,
) -> None:
    conn.execute(
        """INSERT INTO decisions
             (ts, match_id, venue_ticker, side, fair_p, price_c, fee_c, edge,
              action, reason, mode)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (ts, match_id, venue_ticker, side, fair_p, price_c, fee_c, edge,
         action, reason, mode),
    )


def upsert_order(
    conn: psycopg.Connection,
    client_order_id: str,
    venue_ticker: str,
    side: str,
    action: str,
    price_c: int,
    count: int,
    post_only: bool,
    status: str,
    mode: str,
    venue_order_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO orders
             (client_order_id, venue_order_id, venue_ticker, side, action,
              price_c, count, post_only, status, mode, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
           ON CONFLICT (client_order_id) DO UPDATE SET
             venue_order_id = EXCLUDED.venue_order_id,
             status = EXCLUDED.status,
             updated_at = now()""",
        (client_order_id, venue_order_id, venue_ticker, side, action,
         price_c, count, post_only, status, mode),
    )


def insert_fill(
    conn: psycopg.Connection,
    fill_id: str,
    client_order_id: str,
    ts: datetime,
    price_c: int,
    count: int,
    fee_cost_c: int,
    is_taker: bool,
    mode: str,
) -> None:
    conn.execute(
        """INSERT INTO fills
             (fill_id, client_order_id, ts, price_c, count, fee_cost_c, is_taker, mode)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (fill_id) DO NOTHING""",
        (fill_id, client_order_id, ts, price_c, count, fee_cost_c, is_taker, mode),
    )


# -- reads for risk / reconciliation -------------------------------------------

def get_risk_state(conn: psycopg.Connection) -> "Any":
    """Build a RiskState from open orders + venue match mapping.

    Exposure per order = price * count (max loss for buys) + estimated fee is
    ignored here (fees are small; reconcile uses actual fee_cost from fills).
    """
    from ..risk.limits import RiskState

    rows = conn.execute(
        """SELECT o.venue_ticker, o.side, o.price_c, o.count,
                  COALESCE(vm.event_ticker, o.venue_ticker) AS match_key
           FROM orders o
           LEFT JOIN venue_markets vm
             ON vm.venue_ticker = o.venue_ticker AND vm.venue = 'kalshi'
           WHERE o.status IN ('open', 'partial')"""
    ).fetchall()

    state = RiskState()
    for r in rows:
        exposure = (r["price_c"] / 100.0) * r["count"]
        state.exposure_per_match[r["match_key"]] = (
            state.exposure_per_match.get(r["match_key"], 0.0) + exposure
        )
        state.open_exposure_total += exposure
        state.open_orders_count += 1
        state.sides_per_match.setdefault(r["match_key"], set()).add(r["side"])

    # today's exposure includes filled buys too (positions held today)
    today = conn.execute(
        """SELECT COALESCE(SUM(f.price_c * f.count) / 100.0, 0) AS exp
           FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id
           WHERE f.ts::date = now()::date AND o.action = 'buy'"""
    ).fetchone()
    state.exposure_today = float(today["exp"] or 0)

    pnl = conn.execute(
        """SELECT COALESCE(SUM(
                    CASE WHEN o.action = 'buy' THEN -(f.price_c * f.count) / 100.0
                         ELSE (f.price_c * f.count) / 100.0 END
                    - COALESCE(f.fee_cost_c, 0) / 100.0), 0) AS pnl
               FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id
               WHERE f.ts::date = now()::date"""
    ).fetchone()
    state.daily_realized_pnl = float(pnl["pnl"] or 0)
    return state
