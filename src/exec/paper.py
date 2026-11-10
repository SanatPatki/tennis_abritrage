"""Paper executor — simulated fills. See AGENTS.md §10.

- Taker paper fill: fill at the current best opposite price for up to the
  displayed size; remainder unfilled.
- Maker paper fill: filled only when a logged trade prints at or through our
  price AFTER order time, up to that trade's size minus size ahead of us in
  the queue (we assume we were last in queue at our price level).
- Fees via kalshi_fee (§6.2). Flag if maker fill rate > 50%.

All prices in integer cents. Trades are reported in YES-price terms; NO-side
orders are handled by converting (no_price = 100 - yes_price).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..clients.kalshi import kalshi_fee


@dataclass
class PaperOrder:
    order_id: str
    ticker: str
    side: str               # 'yes' | 'no'
    price_c: int
    count: int
    post_only: bool
    placed_at: datetime
    filled: int = 0
    status: str = "open"    # open | filled | partial | cancelled
    is_taker: bool = False
    queue_ahead: float = 0.0  # displayed size ahead of us at our price level


@dataclass
class PaperFill:
    order_id: str
    ts: datetime
    price_c: int
    count: int
    fee_usd: float
    is_taker: bool


class PaperExecutor:
    """Simulated fills against trade prints. No network, fully deterministic."""

    def __init__(self, maker_fee_series: bool = False):
        self.maker_fee_series = maker_fee_series
        self.orders: dict[str, PaperOrder] = {}
        self.fills: list[PaperFill] = []
        self._next_id = 0
        # (ticker, side, price_c) -> remaining queue size ahead of our orders
        self._level_ahead: dict[tuple[str, str, int], float] = {}

    # -- order entry ------------------------------------------------------

    def place_order(
        self,
        ticker: str,
        side: str,
        price_c: int,
        count: int,
        post_only: bool,
        ts: datetime,
        # book context for taker fills / queue position
        best_ask_c: int | None = None,
        best_ask_size: int | None = None,
        level_size: int = 0,
        order_id: str | None = None,
    ) -> PaperOrder:
        self._next_id += 1
        oid = order_id or f"paper-{self._next_id}"
        order = PaperOrder(
            order_id=oid, ticker=ticker, side=side, price_c=price_c,
            count=count, post_only=post_only, placed_at=ts,
            queue_ahead=float(level_size) if post_only else 0.0,
        )
        self.orders[oid] = order
        if post_only and level_size > 0:
            key = (ticker, side, price_c)
            self._level_ahead[key] = self._level_ahead.get(key, 0.0) + level_size

        if not post_only:
            # taker: cross at best ask up to displayed size
            if best_ask_c is not None:
                avail = best_ask_size if best_ask_size is not None else count
                qty = min(count, avail)
                if qty > 0:
                    self._fill(order, qty, ts, is_taker=True)
            order.status = "filled" if order.filled >= count else (
                "partial" if order.filled > 0 else "cancelled"
            )
        return order

    # -- market data --------------------------------------------------------

    def on_trade(self, ticker: str, ts: datetime, yes_price_c: int, size: int) -> list[PaperFill]:
        """Process a trade print (YES-price terms). Returns new fills.

        A print of `size` contracts at YES price `yes_price_c` can fill our
        resting orders whose price is at or through the print:
          - YES buy at p  fills when yes_price_c <= p
          - NO  buy at p  fills when yes_price_c >= 100 - p
        Orders strictly through the print price fill first (price priority).
        Orders at the print price share `size - queue_ahead` contracts — we
        assume we were last in queue at that level (AGENTS.md §10).
        """
        before = len(self.fills)
        candidates = []
        for o in self.orders.values():
            if o.status != "open" or o.ticker != ticker or o.placed_at >= ts:
                continue
            if o.side == "yes":
                if yes_price_c <= o.price_c:
                    through = yes_price_c < o.price_c
                    candidates.append((o, through))
            else:  # no
                no_equiv = 100 - o.price_c
                if yes_price_c >= no_equiv:
                    through = yes_price_c > no_equiv
                    candidates.append((o, through))
        # price priority: deepest book first; through orders before at-price
        candidates.sort(
            key=lambda ot: (
                not ot[1],  # through=True sorts first
                -(ot[0].price_c if ot[0].side == "yes" else 100 - ot[0].price_c),
            )
        )

        remaining = float(size)
        # per-level pool for at-price orders: size minus queue ahead
        level_pool: dict[tuple[str, int], float] = {}
        level_alloc: dict[tuple[str, int], float] = {}
        at_price_levels: set[tuple[str, str, int]] = set()  # (ticker, side, price_c)

        for o, through in candidates:
            if remaining <= 0:
                break
            want = o.count - o.filled
            if want <= 0:
                continue
            if through:
                avail = remaining
            else:
                key = (o.side, o.price_c)
                at_price_levels.add((ticker, o.side, o.price_c))
                if key not in level_pool:
                    ahead = self._level_ahead.get((ticker, o.side, o.price_c), 0.0)
                    level_pool[key] = max(0.0, size - ahead)
                used = level_alloc.get(key, 0.0)
                avail = max(0.0, level_pool[key] - used)
            qty = int(min(want, avail, remaining))
            if qty <= 0:
                continue
            self._fill(o, qty, ts, is_taker=False)
            remaining -= qty
            if not through:
                key = (o.side, o.price_c)
                level_alloc[key] = level_alloc.get(key, 0.0) + qty
        # the print consumes queue-ahead at each touched level, regardless of fills
        for akey in at_price_levels:
            ahead = self._level_ahead.get(akey, 0.0)
            self._level_ahead[akey] = max(0.0, ahead - size)
        return self.fills[before:]

    def cancel(self, order_id: str) -> None:
        o = self.orders.get(order_id)
        if o and o.status == "open":
            o.status = "cancelled"

    # -- internals -----------------------------------------------------------

    def _fill(self, order: PaperOrder, qty: int, ts: datetime, is_taker: bool) -> None:
        fee = kalshi_fee(
            order.price_c / 100, qty, maker=not is_taker,
            maker_fee_series=self.maker_fee_series,
        )
        order.filled += qty
        if order.filled >= order.count:
            order.status = "filled"
        self.fills.append(PaperFill(
            order_id=order.order_id, ts=ts, price_c=order.price_c,
            count=qty, fee_usd=fee, is_taker=is_taker,
        ))

    # -- metrics ---------------------------------------------------------------

    def maker_fill_rate(self) -> float:
        maker_orders = [o for o in self.orders.values() if o.post_only]
        if not maker_orders:
            return 0.0
        filled = sum(1 for o in maker_orders if o.filled > 0)
        return filled / len(maker_orders)
