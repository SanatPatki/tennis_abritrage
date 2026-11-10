# Tennis Prediction-Market Trading Bot

Buys/sells Kalshi tennis match-winner contracts when the Kalshi price differs
from Pinnacle's de-vigged probability by more than fees + buffer.

- **Venue:** Kalshi only for v1 (`KXATPMATCH`, `KXWTAMATCH`). Polymarket US is v2.
- **Pre-match only.** Post-only maker orders by default. `MODE=paper` by default.
- **Main metric:** closing-line value (CLV), not P&L.
- **Operating manual:** see [AGENTS.md](AGENTS.md) — read it before writing code.

## Strategy

Pinnacle's tennis closing line is treated as the best public estimate of match
probability. Kalshi prices lag line moves and show a favorite–longshot bias.
A trade fires when `edge = fair_p − price − fee` exceeds the maker/taker
thresholds in `config.yaml` and all filters pass (odds freshness, match-link
confidence, price band, time-to-start, risk limits).

## Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # fill in keys; MODE stays paper
```

Postgres + app via docker:

```bash
docker compose -f docker/docker-compose.yml up -d
```

## Layout

```
config.yaml            strategy + risk params (no secrets)
src/clients/           Kalshi REST/WS, odds provider, Polymarket US (stub)
src/data/              tennis-data.co.uk + Sackmann loaders
src/match/             name normalization + event linker
src/model/             de-vig, surface Elo
src/strategy/          signal, quoting, sizing
src/exec/              live (env-gated) / paper executors
src/risk/              limits, kill switch, reconciliation
src/db/                schema.sql + migrations
src/backtest/          Stage A calibration, Stage B replay, reports/
src/main.py            scheduler entrypoint
tests/
docker/
```

## Data

- **tennis-data.co.uk** — results + bookmaker odds (PSW/PSL = Pinnacle).
  Cloudflare blocks scripted downloads; fetch manually from
  `alldata.php?year=YYYY&file=atp|wta` into `data/raw/tennis_data/`.
- **Sackmann data** — original repos went 404 in Oct 2026; we use the archive
  mirror `Aneeshers/tennis-sackmann-archive` (CC BY-NC-SA, non-commercial only).
  Already downloaded under `data/raw/sackmann/` (gitignored).

## Status

| Phase | Status |
|---|---|
| 1. Data + Stage A calibration | Done for ATP 2020–2025 (report in `src/backtest/reports/`); WTA + 2015–2019 pending tennis-data downloads |
| 2. Fair value + matching | De-vig + linker implemented ([docs](docs/event-matching.md)); needs API adapters, aliases file, and 200-match accuracy check |
| 3. Paper trading | Not started |
| 4. Live small | Not started — requires go-live gate in AGENTS.md §11 |

## Safety

Live trading is hard-gated: the executor refuses to run unless `MODE=live`
**and** `I_UNDERSTAND_LIVE_TRADING=yes`. Never commit secrets; `.pem` files
live outside the repo. Every decision is logged, including no-trades.

## Tests

```bash
.venv/bin/python -m pytest -q
```
