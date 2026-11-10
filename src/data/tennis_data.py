"""tennis-data.co.uk loader — backtest ground truth. See AGENTS.md §4.10.

Download annual ATP/WTA files manually into data/raw/tennis_data/
(scripted download is blocked by Cloudflare — verified Nov 2026).
Expected names: atp_YYYY.xlsx / wta_YYYY.xlsx (csv also accepted), but any
file matching *{tour}*{year}* or *{year}*{tour}* in the raw dir works.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/tennis_data")


def _find_file(tour: str, year: int, raw_dir: Path) -> Path:
    candidates = [
        raw_dir / f"{tour}_{year}.xlsx",
        raw_dir / f"{tour}_{year}.csv",
        raw_dir / f"{tour}{year}.xlsx",
        raw_dir / f"{year}_{tour}.xlsx",
    ]
    for p in candidates:
        if p.exists():
            return p
    # fallback: any file containing both tokens, e.g. "alldata_2024_atp.xlsx"
    matches = sorted(
        p for p in raw_dir.iterdir()
        if p.is_file() and tour in p.name.lower() and str(year) in p.name
    )
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"no tennis-data file for {tour} {year} under {raw_dir} "
        f"(put files like {tour}_{year}.xlsx there)"
    )


def load_season(tour: str, year: int, raw_dir: str | Path = RAW_DIR) -> pd.DataFrame:
    """Load one season file. `tour` is 'atp' or 'wta'.

    Returns raw winner/loser-oriented rows. Exclude Comment != 'Completed'
    for calibration; keep them for settlement-rule tests.
    """
    path = _find_file(tour.lower(), year, Path(raw_dir))
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def load_all(tour: str, years: range | list[int], raw_dir: str | Path = RAW_DIR) -> pd.DataFrame:
    frames = [load_season(tour, y, raw_dir) for y in years]
    return pd.concat(frames, ignore_index=True)
