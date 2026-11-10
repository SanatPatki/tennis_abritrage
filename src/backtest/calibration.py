"""Stage A calibration: predicted vs realized by bucket. See AGENTS.md §11.

Uses tennis-data.co.uk 2015-present, de-vig PSW/PSL, randomize orientation,
bucket predicted prob into 5% bins, report Brier + log-loss per de-vig method
and per tour/surface. Writes a markdown report to backtest/reports/.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.tennis_data import load_all
from ..model.devig import DEVIG_METHODS

REPORTS_DIR = Path(__file__).parent / "reports"
MIN_YEAR = 2015


@dataclass
class CalibrationResult:
    method: str
    tour: str | None      # None = pooled
    surface: str | None   # None = pooled
    n: int
    brier: float
    log_loss: float
    buckets: pd.DataFrame  # columns: bin, n, mean_pred, realized_freq


def _orientation_samples(df: pd.DataFrame, p_win: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Randomize orientation so the model can't exploit winner/loser ordering.

    Rows are winner/loser-oriented. For each match we emit one sample:
    predicted prob q and realized r, where with prob 0.5 the "player 1" is the
    winner (q = p_win, r = 1) and otherwise the loser (q = 1 - p_win, r = 0).
    """
    flip = rng.random(len(df)) < 0.5
    q = np.where(flip, 1.0 - p_win, p_win)
    r = np.where(flip, 0.0, 1.0).astype(float)
    return q, r


def _metrics(q: np.ndarray, r: np.ndarray) -> tuple[float, float]:
    eps = 1e-15
    qc = np.clip(q, eps, 1 - eps)
    brier = float(np.mean((qc - r) ** 2))
    log_loss = float(-np.mean(r * np.log(qc) + (1 - r) * np.log(1 - qc)))
    return brier, log_loss


def _bucket_table(q: np.ndarray, r: np.ndarray, width: float = 0.05) -> pd.DataFrame:
    edges = np.arange(0.0, 1.0 + width, width)
    idx = np.clip(np.digitize(q, edges) - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        mask = idx == b
        n = int(mask.sum())
        if n:
            rows.append({
                "bin": f"{edges[b]:.2f}-{edges[b+1]:.2f}",
                "n": n,
                "mean_pred": float(q[mask].mean()),
                "realized_freq": float(r[mask].mean()),
            })
    return pd.DataFrame(rows)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and keep only completed matches with Pinnacle odds."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # tolerate common column-name variants
    rename = {}
    for want, cands in {
        "Date": ["Date"],
        "Comment": ["Comment"],
        "Surface": ["Surface"],
        "PSW": ["PSW", "PinnacleW", "PSWp"],
        "PSL": ["PSL", "PinnacleL", "PSLp"],
        "Tour": ["Tour", "Series", "ATP/WTA"],
    }.items():
        for c in cands:
            if c in df.columns and want not in df.columns:
                rename[c] = want
                break
    df = df.rename(columns=rename)
    for col in ("PSW", "PSL"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    mask = (
        df["Comment"].astype(str).str.strip().str.lower().eq("completed")
        & df["PSW"].notna() & df["PSL"].notna()
        & (df["PSW"] > 1.0) & (df["PSL"] > 1.0)
    )
    return df.loc[mask].reset_index(drop=True)


def run_calibration(
    years: range | list[int] | None = None,
    tours: tuple[str, ...] = ("atp", "wta"),
    seed: int = 42,
    out_dir: Path | None = None,
) -> list[CalibrationResult]:
    """Run Stage A calibration. Returns results; writes markdown report."""
    if years is None:
        last_full = date.today().year - 1
        years = range(MIN_YEAR, last_full + 1)
    rng = np.random.default_rng(seed)

    frames = []
    for tour in tours:
        df = load_all(tour, list(years))
        df["_tour"] = tour.upper()
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    df = _prepare(raw)
    if df.empty:
        raise ValueError("no completed matches with Pinnacle odds found — check data/raw/tennis_data/")

    results: list[CalibrationResult] = []
    o1 = df["PSW"].to_numpy(float)  # decimal odds, winner side
    o2 = df["PSL"].to_numpy(float)  # loser side

    for method_name, devig in DEVIG_METHODS.items():
        if method_name == "shin":
            continue  # not implemented yet
        p_win = np.array([devig(a, b)[0] for a, b in zip(o1, o2)])
        q_all, r_all = _orientation_samples(df, p_win, rng)

        slices: list[tuple[str | None, str | None, np.ndarray]] = [
            (None, None, np.ones(len(df), dtype=bool)),
        ]
        for tour in sorted(df["_tour"].unique()):
            slices.append((tour, None, (df["_tour"] == tour).to_numpy()))
        if "Surface" in df.columns:
            for surf in sorted(df["Surface"].dropna().unique()):
                slices.append((None, str(surf), (df["Surface"] == surf).to_numpy()))

        for tour_name, surf_name, mask in slices:
            q, r = q_all[mask], r_all[mask]
            if len(q) < 30:
                continue
            brier, ll = _metrics(q, r)
            results.append(CalibrationResult(
                method=method_name, tour=tour_name, surface=surf_name,
                n=len(q), brier=brier, log_loss=ll,
                buckets=_bucket_table(q, r),
            ))

    _write_report(results, df, years, out_dir)
    return results


def _write_report(results, df, years, out_dir=None) -> Path:
    out_dir = Path(out_dir) if out_dir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{date.today().isoformat()}-calibration.md"

    lines = [
        f"# Stage A calibration — {date.today().isoformat()}",
        "",
        f"- Matches used: {len(df)} completed matches with Pinnacle odds",
        f"- Seasons: {min(years)}–{max(years)}",
        "- Orientation randomized per AGENTS.md §4.10",
        "",
        "## Summary (pooled)",
        "",
        "| method | n | Brier | log-loss |",
        "|---|---|---|---|",
    ]
    for res in results:
        if res.tour is None and res.surface is None:
            lines.append(f"| {res.method} | {res.n} | {res.brier:.4f} | {res.log_loss:.4f} |")
    lines += ["", "## By tour / surface", "",
              "| method | slice | n | Brier | log-loss |", "|---|---|---|---|---|"]
    for res in results:
        if res.tour is not None or res.surface is not None:
            sl = res.tour or res.surface or ""
            lines.append(f"| {res.method} | {sl} | {res.n} | {res.brier:.4f} | {res.log_loss:.4f} |")

    # bucket detail for the default method, pooled
    default = next((r for r in results if r.method == "multiplicative"
                    and r.tour is None and r.surface is None), None)
    if default is not None:
        lines += ["", "## Calibration buckets (multiplicative, pooled)", "",
                  "| predicted bin | n | mean pred | realized freq |",
                  "|---|---|---|---|"]
        for _, row in default.buckets.iterrows():
            lines.append(f"| {row['bin']} | {row['n']} | {row['mean_pred']:.3f} | {row['realized_freq']:.3f} |")

    path.write_text("\n".join(lines) + "\n")
    return path


if __name__ == "__main__":
    results = run_calibration()
    for r in results:
        if r.tour is None and r.surface is None:
            print(f"{r.method}: n={r.n} brier={r.brier:.4f} logloss={r.log_loss:.4f}")
