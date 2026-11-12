# Tennis Arbitrage Bot

Trades Kalshi tennis markets against Pinnacle's odds. When Kalshi's price
differs from Pinnacle's de-vigged probability by more than fees + buffer,
it buys the underpriced side.

> **Status: paper trading only.** `MODE=paper` is the default and live
> trading is hard-gated behind two env flags. See [Safety](#safety).

## How it works

```
Pinnacle odds ──► de-vig ──► fair probability
                              │
Kalshi order book ──► best bid/ask ──► edge = fair_p − price − fee
                              │
                    edge ≥ threshold? ──► risk checks ──► paper/live order
```

- **Pre-match only** — all orders cancelled before match start
- **Maker-first** — post-only limit orders; taker only on large edge
- **Main metric** — closing-line value (CLV), not raw P&L

## Quickstart

```bash
# 1. Python 3.11+ venv
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Env (already created locally; copy .env.example for reference)
cp .env.example .env   # fill in keys when you have them

# 3. Postgres (or: docker compose -f docker/docker-compose.yml up -d)
brew services start postgresql@16   # already installed on this machine

# 4. Check config — prints what's missing
python -m src.config

# 5. Tests
pytest -q
```

## Repo map

| Path | What it does |
|---|---|
| `config.yaml` | All strategy/risk params — no secrets |
| `src/clients/` | Kalshi REST client (signing done), WS stub, odds provider stub |
| `src/data/` | tennis-data.co.uk + Sackmann CSV loaders |
| `src/match/` | Name normalization + event linker → `docs/event-matching.md` |
| `src/model/` | De-vig methods, surface Elo |
| `src/strategy/` | Edge signal, maker quoting, Kelly sizing |
| `src/exec/` | `paper.py` fill simulator · `live.py` env-gated |
| `src/risk/` | Pre-trade limits, kill switch, reconciliation |
| `src/db/` | Postgres schema + migrations + repository |
| `src/backtest/` | Stage A calibration (done) · Stage B replay |
| `src/main.py` | APScheduler entrypoint — all §12 jobs registered |
| `src/dashboard/` | Read-only web UI → `python -m src.dashboard.app` → http://127.0.0.1:8080 |
| `tests/` | 40+ unit/integration tests, no real network calls |
| `AGENTS.md` | **Operating manual — read before changing anything** |

## Roadmap status

| Phase | Status |
|---|---|
| 1. Data + calibration | ✅ ATP 2020–25 calibrated ([report](src/backtest/reports/2026-11-10-calibration.md)); WTA pending downloads |
| 2. Fair value + matching | ✅ De-vig, linker, Elo done — needs live API data for the 200-match check |
| 3. Paper trading | 🟡 All components built (quoting, paper fills, risk, DB, scheduler) — needs API keys to run the loop |
| 4. Live small | ⬜ Blocked by go-live gate (≥200 paper trades, positive CLV) |

## Safety

- Live orders require **both** `MODE=live` in config **and**
  `I_UNDERSTAND_LIVE_TRADING=yes` in env — the executor refuses otherwise
- Secrets only from env vars; `.pem` keys live outside the repo
- Every decision logged to the `decisions` table, including skips
- Kill switch: any risk breach → cancel all, `/tmp/KILL` lock, alert

## Docs

- [AGENTS.md](AGENTS.md) — full operating manual (strategy, APIs, formulas, risk, phases)
- [docs/event-matching.md](docs/event-matching.md) — how the linker works
- `.env.example` — required environment variables
