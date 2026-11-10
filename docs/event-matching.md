# Event matching / linker

Implements AGENTS.md §5 — the hardest part of the system. Every trade depends
on correctly linking three things: a **Kalshi market**, an **odds fixture**
(Pinnacle prices via the odds provider), and eventually a **result**.

Code: `src/match/linker.py`. Tests: `tests/test_linker.py`.

## Inputs

The linker is venue-agnostic. Adapters convert API responses / DB rows into:

```python
VenueSide(
    venue_ticker="KXATPMATCH-26NOV15SINFRI",   # market whose YES = this player
    event_ticker="KXATPMATCH-26NOV15SINFRI",   # event grouping the two markets
    player_name="Jannik Sinner",               # raw name as listed by the venue
    tour="ATP",                                # 'ATP' | 'WTA'
    tournament="ATP Finals",                   # best-effort tournament name
    scheduled_start=datetime(..., tzinfo=utc), # REQUIRED — see below
)

OddsFixture(
    fixture_id="oddspapi-12345",
    p1_name="Jannik Sinner",                   # outcome 1
    p2_name="Taylor Fritz",                    # outcome 2
    tour="ATP",
    tournament="ATP Finals",
    start_time=datetime(..., tzinfo=utc),
)
```

Each Kalshi match event produces **two** `VenueSide`s (one per player market).
Events that don't have exactly two sides are skipped.

## Candidate filtering

A venue event and an odds fixture are only compared when:

- `tour` matches exactly (`ATP`/`WTA`)
- both start times are known and within **±12 h** of each other
- **if either start time is missing, the pair is never linked** —
  AGENTS.md §1.2 says unknown start ⇒ do not trade, so we don't even store it

## Confidence score

```
confidence = 0.70 * name_score + 0.20 * tournament_score + 0.10 * time_score
```

- **name_score** — mean of the best two-player assignment (order-independent):
  `max(direct, swapped)`. Each player pair uses
  `max(token_sort_ratio, token_set_ratio) / 100`, evaluated both raw and with
  single-letter initials stripped, so all of these match:
  - `Jannik Sinner` ↔ `Sinner J.` (tennis-data "Lastname F." format)
  - `Felix Auger-Aliassime` ↔ `Auger Aliassime F.`
  - `Nicolás Jarry` ↔ `Nicolas Jarry` (diacritics via `unidecode`)
- **tournament_score** — `token_sort_ratio` on normalized names; neutral 0.5
  when either side is missing
- **time_score** — `1 − |Δt| / 12h`, clamped to [0,1]

## Thresholds (AGENTS.md §5)

| confidence | result |
|---|---|
| ≥ 0.95 | `auto=True`, `tradable=True` — safe to trade |
| 0.80 – 0.95 | stored in results with `tradable=False` — flagged, **never trade** |
| < 0.80 | ignored entirely |

Phase 2's done-criteria requires ≥99% correct links on a hand-checked sample
of 200 matches before this gate is trusted.

## Player orientation

`LinkResult.yes_is_odds_p1_ticker` is the `venue_ticker` of the Kalshi market
whose **YES = odds outcome 1** (`OddsFixture.p1_name`). It's computed by
independent per-player name matching, so fixture player order doesn't matter —
verified by `test_swapped_orientation_maps_correct_ticker`.

Downstream code must use this field, never assume market order matches fixture
order.

## Aliases

Known name exceptions live in `data/player_aliases.csv`
(`canonical_name, alias, source`). Pass the path to `MatchLinker(aliases_path=...)`;
aliases are applied after normalization, before scoring.

## Usage

```python
from src.match.linker import MatchLinker, VenueSide, OddsFixture

linker = MatchLinker(aliases_path="data/player_aliases.csv")
results = linker.link(venue_sides, fixtures)

for r in results:
    if not r.tradable:
        continue  # flagged links must not trade
    # r.yes_is_odds_p1_ticker -> Kalshi market aligned with odds p1
    # the OTHER side's ticker is the NO-equivalent market
```

## Persistence

`link()` returns `LinkResult`s; the caller writes `match_links` rows
(`match_id`, `odds_fixture_id`, `confidence`, `method`, `created_at`) once the
DB layer lands. `method` should record e.g. `"fuzzy-v1"` plus the score
breakdown in `scores` for auditability.

## Known limitations

- Two-player events only — doubles are out of scope for v1 anyway.
- Names that fuzzy-match well but are actually different players (e.g. father/
  son with same surname) rely on the tournament+time terms and the 0.95 gate;
  the 200-match hand-check in Phase 2 exists to catch residual errors.
- `VenueSide.player_name` must come from the venue's market/event title —
  the Kalshi adapter (not yet written) is responsible for extracting it.
