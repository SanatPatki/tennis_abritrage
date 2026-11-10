"""Kalshi market <-> odds fixture <-> results linker. See AGENTS.md §5.

confidence >= 0.95 auto-links; 0.80-0.95 stored but flagged (no trading);
below ignored. Orientation: explicitly maps which Kalshi market (YES = player X)
corresponds to odds outcome 1 vs 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz

from .normalize import load_aliases, name_keys, normalize

AUTO_LINK = 0.95
FLAG_LINK = 0.80
TIME_WINDOW_H = 12.0

# score weights — player names dominate; tournament and time are tiebreakers
W_PLAYER = 0.70
W_TOURNAMENT = 0.20
W_TIME = 0.10


@dataclass
class VenueSide:
    """One player side of a Kalshi match event (one market per player)."""

    venue_ticker: str
    event_ticker: str
    player_name: str
    tour: str            # 'ATP' | 'WTA'
    tournament: str | None = None
    scheduled_start: datetime | None = None


@dataclass
class OddsFixture:
    fixture_id: str
    p1_name: str
    p2_name: str
    tour: str
    tournament: str | None = None
    start_time: datetime | None = None


@dataclass
class LinkResult:
    venue_event: str
    fixture_id: str
    confidence: float
    auto: bool                    # >= AUTO_LINK
    tradable: bool                # >= AUTO_LINK only; flagged links never trade
    # venue_ticker of the market whose YES = odds outcome 1 (p1)
    yes_is_odds_p1_ticker: str
    scores: dict = field(default_factory=dict)


def _strip_initials(s: str) -> str:
    """Drop single-letter tokens ('Sinner J.' -> 'sinner'; 'Auger Aliassime F.' -> 'auger aliassime')."""
    return " ".join(t for t in s.split() if len(t) > 1)


def _name_score(a: str, b: str) -> float:
    """Best fuzzy score between two player names, 0-1.

    Tries token_sort and token_set (handles 'Sinner J.' vs 'Jannik Sinner'),
    with and without single-letter initials stripped.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0

    def best(x: str, y: str) -> float:
        return max(fuzz.token_sort_ratio(x, y), fuzz.token_set_ratio(x, y)) / 100.0

    return max(
        best(na, nb),
        best(_strip_initials(na), _strip_initials(nb)),
    )


def _pair_score(k_names: list[str], f_names: list[str]) -> float:
    """Best assignment of 2 kalshi players to 2 fixture players (order-independent)."""
    direct = (_name_score(k_names[0], f_names[0]) + _name_score(k_names[1], f_names[1])) / 2
    swapped = (_name_score(k_names[0], f_names[1]) + _name_score(k_names[1], f_names[0])) / 2
    return max(direct, swapped)


def _tournament_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.5  # neutral when missing — don't punish unknowns
    return fuzz.token_sort_ratio(normalize(a), normalize(b)) / 100.0


def _time_score(t1: datetime | None, t2: datetime | None) -> float:
    if t1 is None or t2 is None:
        return 0.5
    hours = abs((t1 - t2).total_seconds()) / 3600.0
    if hours > TIME_WINDOW_H:
        return 0.0
    return 1.0 - hours / TIME_WINDOW_H


class MatchLinker:
    """Links Kalshi match events to odds fixtures.

    Input records are venue-agnostic dataclasses; adapters populate them from
    Kalshi API responses / odds provider fixtures / DB rows.
    """

    def __init__(self, aliases_path: str | Path | None = None):
        self.aliases = load_aliases(str(aliases_path)) if aliases_path else {}

    def _canon(self, name: str) -> str:
        n = normalize(name)
        return self.aliases.get(n, name)  # alias -> canonical display name

    def _canonical_names(self, names: list[str]) -> list[str]:
        return [self._canon(n) for n in names]

    def link(
        self,
        venue_sides: list[VenueSide],
        fixtures: list[OddsFixture],
    ) -> list[LinkResult]:
        """Return LinkResults for candidate pairs. Caller persists match_links."""
        # group venue sides by event
        events: dict[str, list[VenueSide]] = {}
        for s in venue_sides:
            events.setdefault(s.event_ticker, []).append(s)

        results: list[LinkResult] = []
        for event_ticker, sides in events.items():
            if len(sides) != 2:
                continue  # not a two-player match market
            tour = sides[0].tour
            k_names = self._canonical_names([s.player_name for s in sides])
            start = sides[0].scheduled_start
            tournament = sides[0].tournament

            best: LinkResult | None = None
            best_score = -1.0
            for fx in fixtures:
                if fx.tour != tour:
                    continue
                if start and fx.start_time and abs((start - fx.start_time).total_seconds()) > TIME_WINDOW_H * 3600:
                    continue
                if not start or not fx.start_time:
                    continue  # can't verify timing — spec: unknown start => don't trade

                name_score = _pair_score(k_names, [fx.p1_name, fx.p2_name])
                ts = _tournament_score(tournament, fx.tournament)
                xs = _time_score(start, fx.start_time)
                conf = W_PLAYER * name_score + W_TOURNAMENT * ts + W_TIME * xs

                if conf > best_score:
                    # which kalshi market YES = odds p1 (independent per-player match)
                    p1_venue_ticker = self._venue_for_player(sides, fx.p1_name)
                    best_score = conf
                    best = LinkResult(
                        venue_event=event_ticker,
                        fixture_id=fx.fixture_id,
                        confidence=conf,
                        auto=conf >= AUTO_LINK,
                        tradable=conf >= AUTO_LINK,
                        yes_is_odds_p1_ticker=p1_venue_ticker,
                        scores={"name": name_score, "tournament": ts, "time": xs},
                    )
            if best is not None and best.confidence >= FLAG_LINK:
                results.append(best)
        return results

    def _venue_for_player(self, sides: list[VenueSide], target_name: str) -> str:
        """Return the venue_ticker whose YES player best matches target_name."""
        best_side, best_s = sides[0], -1.0
        for s in sides:
            sc = _name_score(s.player_name, target_name)
            if sc > best_s:
                best_side, best_s = s, sc
        return best_side.venue_ticker
