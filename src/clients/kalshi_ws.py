"""Kalshi WebSocket client. See AGENTS.md §4.6.

v1 may use REST polling instead; WS is required only once maker requoting is live.
"""

from __future__ import annotations


class KalshiWS:
    """TODO: signed WS upgrade, subscribe orderbook_delta/ticker/fill,
    sequence-gap handling (drop book, resubscribe, wait for snapshot),
    reconnect with backoff capped at 30 s."""

    PROD_WS = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    DEMO_WS = "wss://demo-api.kalshi.co/trade-api/ws/v2"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("kalshi_ws not implemented yet — v1 uses REST polling")
