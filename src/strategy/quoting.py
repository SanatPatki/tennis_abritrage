"""Maker price selection and requote logic. See AGENTS.md §2, §12.

Maker quote: post-only bid at min(best_bid + 1c, fair_p - fee - MIN_EDGE_MAKER).
Requote when fair value moves > REQUOTE_THRESHOLD or every REQUOTE_INTERVAL_SEC.
Use Kalshi `amend` instead of cancel+new where possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..clients.kalshi import kalshi_fee

CENT = 0.01
MIN_PRICE_C, MAX_PRICE_C = 1, 99  # Kalshi valid range: 1c-99c


@dataclass
class QuoteDecision:
    """Result of evaluating whether/how to quote a market."""

    action: str            # 'place' | 'amend' | 'cancel' | 'hold'
    price_c: int | None    # post-only bid price in cents
    reason: str            # e.g. QUOTE_OK, NO_EDGE, PRICE_OUT_OF_RANGE, REQUOTE_DUE


@dataclass
class OpenQuote:
    """State of our resting order on one market side."""

    venue_ticker: str
    side: str              # 'yes' | 'no'
    price_c: int
    count: int
    placed_at: datetime
    last_fair_p: float


class Quoter:
    """Decides maker quote prices and when to requote.

    Config values passed in (from config.yaml):
      min_edge_maker, min_price, max_price, requote_threshold,
      requote_interval_sec, maker_fee_series
    """

    def __init__(
        self,
        min_edge_maker: float,
        min_price: float,
        max_price: float,
        requote_threshold: float,
        requote_interval_sec: int,
        maker_fee_series: bool = False,
    ):
        self.min_edge_maker = min_edge_maker
        self.min_price = min_price
        self.max_price = max_price
        self.requote_threshold = requote_threshold
        self.requote_interval_sec = requote_interval_sec
        self.maker_fee_series = maker_fee_series

    def quote_price_c(
        self,
        fair_p: float,
        best_bid_c: int | None,
        side: str,
        contracts: int = 1,
    ) -> int | None:
        """Maker bid price in cents, or None if no positive-edge quote exists.

        price = min(best_bid + 1c, fair_p - fee - MIN_EDGE_MAKER), floored to cents.
        For side='no', fair_p is the NO-side probability (1 - yes_fair_p).
        """
        fee = kalshi_fee(
            # fee depends on price; iterate once since fee is tiny and price-dependent
            0.5, contracts, maker=True, maker_fee_series=self.maker_fee_series,
        )
        # edge target in probability -> price ceiling
        ceiling = fair_p - fee - self.min_edge_maker
        if ceiling <= 0:
            return None
        ceiling_c = int(ceiling * 100)  # floor to whole cents
        if best_bid_c is not None:
            target_c = min(best_bid_c + 1, ceiling_c)
        else:
            target_c = ceiling_c
        target_c = max(MIN_PRICE_C, min(MAX_PRICE_C, target_c))
        # respect configured price band
        lo_c, hi_c = int(self.min_price * 100), int(self.max_price * 100)
        if target_c < lo_c or target_c > hi_c:
            return None
        # verify edge at the actual (floored) price with real fee
        price = target_c / 100
        real_fee = kalshi_fee(price, contracts, maker=True,
                              maker_fee_series=self.maker_fee_series)
        if fair_p - price - real_fee < self.min_edge_maker:
            return None
        return target_c

    def evaluate(
        self,
        open_quote: OpenQuote | None,
        fair_p: float,
        best_bid_c: int | None,
        now: datetime,
        side: str = "yes",
        contracts: int = 1,
    ) -> QuoteDecision:
        """Decide place/amend/cancel/hold given current fair value and book."""
        desired_c = self.quote_price_c(fair_p, best_bid_c, side, contracts)

        if open_quote is None:
            if desired_c is None:
                return QuoteDecision("hold", None, "NO_EDGE")
            return QuoteDecision("place", desired_c, "QUOTE_OK")

        # we have a resting quote
        if desired_c is None:
            # edge gone or price left the band -> pull the quote
            return QuoteDecision("cancel", None, "EDGE_GONE")

        drift = abs(fair_p - open_quote.last_fair_p)
        stale = (now - open_quote.placed_at) > timedelta(
            seconds=self.requote_interval_sec
        )
        price_moved = desired_c != open_quote.price_c

        if price_moved and (drift > self.requote_threshold or stale):
            return QuoteDecision("amend", desired_c, "REQUOTE")
        if price_moved and not stale and drift <= self.requote_threshold:
            # small drift, don't churn the queue position
            return QuoteDecision("hold", open_quote.price_c, "DRIFT_SMALL")
        if stale and not price_moved:
            # refresh timestamp without changing price -> treat as hold
            return QuoteDecision("hold", open_quote.price_c, "REQUOTE_INTERVAL")
        return QuoteDecision("hold", open_quote.price_c, "QUOTE_OK")
