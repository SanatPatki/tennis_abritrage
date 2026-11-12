# Dashboard

**Status: built.** Read-only FastAPI app + static page, localhost-only.

Run it:

```bash
DATABASE_URL_RO=postgresql://bot_ro:bot_ro@localhost:5432/tennis \
  .venv/bin/python -m src.dashboard.app   # serves http://127.0.0.1:8080
```

Panels: status header (mode, maintenance window, kill-switch lock), risk
cards (P&L, exposure, open orders), match board (book vs fair vs edge vs
link confidence), open orders, recent decisions, recent fills. Auto-refreshes.

DB access uses the SELECT-only `bot_ro` role (`DATABASE_URL_RO`, falls back
to `DATABASE_URL`). The UI can never write.

Read-only web UI over the bot's Postgres state. No trading controls in v1 —
placing/cancelling orders stays in `main.py` code paths only.

## What it shows

| Panel | Source | Refresh |
|---|---|---|
| Status header | config MODE, kill-switch lock (`/tmp/KILL`), maintenance window, scheduler job health | 5 s |
| Today's P&L / exposure | `fills`, `orders`, `decisions` | 15 s |
| Open orders | `orders` (status open/partial) | 15 s |
| Recent decisions | `decisions` latest N, with reason codes | 15 s |
| Match board | `venue_markets` + latest `book_snapshots` + `odds_snapshots` → implied edge per match | 30 s |
| CLV tracker | entry price vs closing snapshot per settled match | on settle |

## Architecture

```
browser ──► dashboard app ──► Postgres (read-only role)
                │
                └── /tmp/KILL flag, config.yaml (read-only)
```

- **Backend:** FastAPI (already-async stack) or Streamlit. Serves JSON + one page.
- **DB:** new read-only Postgres role `bot_ro` with SELECT-only grants — the UI
  can never write.
- **Auth:** bind to localhost only for v1; if exposed later, put it behind the
  same env-gated pattern (no public bind by default).
- **Placement:** `src/dashboard/` package + `python -m src.dashboard` entrypoint,
  own port (default 8501 or 8080), never started by `main.py` scheduler.

## Build order

1. Read-only DB role + repo queries (`get_risk_state`, recent decisions, open orders)
2. Status header + today's P&L (highest value, smallest scope)
3. Match board with live edge column
4. CLV tracker after settlements exist

## Open questions

- Stack: Streamlit (fastest to build, uglier) vs FastAPI + small static page (nicer, more work)
- Port/auth expectations — localhost-only OK?
