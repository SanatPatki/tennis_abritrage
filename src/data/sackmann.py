"""Jeff Sackmann data loader (Elo features). See AGENTS.md §4.11.

Original repos github.com/JeffSackmann/tennis_atp|tennis_wta went 404 in
Oct 2026; we use the archival mirror Aneeshers/tennis-sackmann-archive
(snapshot of upstream June 2026, through 2026 season).
License CC BY-NC-SA — non-commercial use only.
"""

from __future__ import annotations

import pandas as pd


def _find(tour: str, name: str, local_dir: str):
    """Accept both flat ({dir}/atp_matches_2024.csv) and per-tour
    ({dir}/atp/atp_matches_2024.csv) layouts."""
    from pathlib import Path

    for path in (
        Path(local_dir) / name,
        Path(local_dir) / tour / name,
    ):
        if path.exists():
            return path
    raise FileNotFoundError(f"{name} not found under {local_dir} (tour={tour})")


def load_matches(tour: str, year: int, local_dir: str = "data/raw/sackmann") -> pd.DataFrame:
    """Load atp_matches_YYYY.csv / wta_matches_YYYY.csv."""
    path = _find(tour, f"{tour}_matches_{year}.csv", local_dir)
    return pd.read_csv(path, low_memory=False)


def load_players(tour: str, local_dir: str = "data/raw/sackmann") -> pd.DataFrame:
    path = _find(tour, f"{tour}_players.csv", local_dir)
    return pd.read_csv(path, low_memory=False)
