"""Surface Elo — filter only, not the primary signal. See AGENTS.md §3.

Fit on Sackmann match data (winner/loser oriented). Maintains a per-surface
rating plus an all-surface rating; prediction blends them weighted by how many
matches the player has on that surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

ALL_SURFACE = "ALL"
DEFAULT_RATING = 1500.0
MIN_SURFACE_MATCHES = 5  # below this, lean on the all-surface rating


@dataclass
class SurfaceElo:
    """Per-surface Elo ratings keyed by (player_id, surface).

    `surface` values are lowercased ('hard', 'clay', 'grass', 'carpet', ...).
    """

    k_factor: float = 32.0
    ratings: dict[tuple[int, str], float] = field(default_factory=dict)
    matches_played: dict[tuple[int, str], int] = field(default_factory=dict)

    # -- internals -----------------------------------------------------

    def _rating(self, pid: int, surface: str) -> float:
        return self.ratings.get((pid, surface), DEFAULT_RATING)

    def _bump(self, pid: int, surface: str, delta: float) -> None:
        key = (pid, surface)
        self.ratings[key] = self._rating(pid, surface) + delta
        self.matches_played[key] = self.matches_played.get(key, 0) + 1

    @staticmethod
    def _expected(ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    # -- fitting ---------------------------------------------------------

    def update_match(self, winner_id: int, loser_id: int, surface: str) -> None:
        """One completed match: winner_id beat loser_id on `surface`."""
        surface = str(surface).strip().lower()
        surfaces = {surface, ALL_SURFACE}
        for s in surfaces:
            rw = self._rating(winner_id, s)
            rl = self._rating(loser_id, s)
            e_w = self._expected(rw, rl)
            self._bump(winner_id, s, self.k_factor * (1.0 - e_w))
            self._bump(loser_id, s, self.k_factor * (0.0 - (1.0 - e_w)))

    def fit(self, matches: pd.DataFrame, date_col: str = "tourney_date") -> "SurfaceElo":
        """Fit chronologically on a Sackmann matches dataframe.

        Expects columns: winner_id, loser_id, surface, tourney_date (yyyymmdd).
        """
        df = matches.sort_values(date_col, kind="stable")
        for row in df.itertuples(index=False):
            self.update_match(int(row.winner_id), int(row.loser_id), row.surface)
        return self

    # -- prediction ------------------------------------------------------

    def _blended_rating(self, pid: int, surface: str) -> float:
        """Surface rating if enough matches on it, else shrink toward ALL."""
        n_surface = self.matches_played.get((pid, surface), 0)
        r_surface = self._rating(pid, surface)
        r_all = self._rating(pid, ALL_SURFACE)
        if n_surface >= MIN_SURFACE_MATCHES:
            # weight surface rating by evidence; ALL rating as prior
            w = min(n_surface / (n_surface + 10.0), 0.9)
            return w * r_surface + (1 - w) * r_all
        return r_all

    def win_prob(self, player_a: int, player_b: int, surface: str) -> float:
        """P(player_a beats player_b on `surface`)."""
        surface = str(surface).strip().lower()
        ra = self._blended_rating(player_a, surface)
        rb = self._blended_rating(player_b, surface)
        return self._expected(ra, rb)

    def rating(self, player_id: int, surface: str | None = None) -> float:
        return self._rating(player_id, surface or ALL_SURFACE)
