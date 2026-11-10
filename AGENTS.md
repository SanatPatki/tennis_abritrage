# AGENTS.md — Tennis Prediction-Market Trading Bot

Operating manual for any agent working in this repo. Read the whole file before writing code. Items marked **[VERIFY]** were true when this file was written (Nov 2026) but change often; confirm against live docs before relying on them.

---

## 0. TL;DR for agents

- Strategy: buy/sell Kalshi tennis match-winner contracts when the Kalshi price differs from Pinnacle's de-vigged probability by more than fees + buffer.
- Venue: Kalshi only for v1. Polymarket US is v2. Never use international polymarket.com (US persons are blocked).
- Pre-match only. Maker (post-only limit) orders by default. `MODE=paper` by default.
- Main metric is closing-line value (CLV), not P&L.
- If you are unsure whether something can lose real money, stop and ask.

---

## 1. Hard rules (never violate)

1. **`MODE` defaults to `paper`.** Code must refuse to send a live order unless `MODE=live` AND env `I_UNDERSTAND_LIVE_TRADING=yes`. Never change these defaults in a PR.
2. **Pre-match only.** No new orders after `scheduled_start - CANCEL_BEFORE_START_SEC`. At that moment, cancel every resting order on that match. If start time is unknown, do not trade the match.
3. **Post-only by default.** Every order sets `post_only: true` unless the strategy explicitly chose taker AND `edge_after_taker_fee >= MIN_EDGE_TAKER`.
4. **Risk limits are checked before every order** (§9). Any breach → kill switch: cancel all, block new orders, alert.
5. **Secrets only from env.** Never log, print, commit, or put keys in test fixtures. `.pem` files live outside the repo.
6. **No cross-venue "hedges"** unless settlement rules for both legs are verified identical for that specific market (§7).
7. **Every decision is logged** to `decisions` table, including no-trade decisions and their reason code.
8. **Never hardcode tickers or guess them.** Discover via the API (§4.4).
9. **Idempotency:** every order has a unique `client_order_id`; retries reuse the same id.
10. **Do not trade ITF or doubles in v1.** ATP and WTA main-tour singles only (`KXATPMATCH`, `KXWTAMATCH`).

---

## 2. Strategy spec

**Thesis.** Pinnacle's tennis closing line is the best public estimate of match probability. Kalshi prices (a) lag Pinnacle line moves, and (b) show a favorite–longshot bias: cheap contracts win less often than their price implies, expensive ones slightly more (Bürgi, Deng & Whelan, 300k Kalshi contracts; takers averaged ~−32%, makers ~−10%).

**Signal (per player side of each match):**
```
fair_p      = de-vigged Pinnacle probability (§6.1)
buy_price   = best YES ask you'd pay (or your maker bid price)
fee         = kalshi_fee(price, maker|taker)          (§6.2)
edge_buy    = fair_p - buy_price - fee
```
Also evaluate the NO side (equivalent to selling YES): `edge_no = (1 - fair_p) - no_price - fee`.

**Trade when:** `edge >= MIN_EDGE_MAKER` (maker) or `>= MIN_EDGE_TAKER` (taker), AND all filters pass:
- Pinnacle odds updated within `MAX_ODDS_AGE_SEC`.
- Kalshi market `status` is open and `close_time` is after now.
- Match confidence from event matching ≥ `MIN_MATCH_CONFIDENCE` (§5).
- Price within `[MIN_PRICE, MAX_PRICE]` (default 0.10–0.90; avoids longshot zone and illiquid tails).
- Time to start between `MIN_TIME_TO_START` and `MAX_TIME_TO_START`.

**Maker quoting:** place a post-only bid at `min(best_bid + 1¢, fair_p - fee - MIN_EDGE_MAKER)`. Requote when fair value moves more than `REQUOTE_THRESHOLD` or every `REQUOTE_INTERVAL_SEC`. Use Kalshi `amend` instead of cancel+new where possible.

**Out of scope for v1:** in-play, set/game markets (`KXATPSETWINNER`, `KXATPGAMETOTAL`, etc.), tournament winner (`KXATP`, `KXWTA`), Challenger (`KXATPCHALLENGERMATCH`, `KXWTACHALLENGERMATCH`), doubles (`KXATPDOUBLES`).

---

## 3. Repo layout

```
config.yaml              strategy + risk params (no secrets)
.env.example             names of required env vars, no values
src/
  clients/
    kalshi.py            REST client: signing, retries, rate limit
    kalshi_ws.py         WebSocket client: orderbook_delta, ticker, fill
    odds.py              odds provider adapter (OddsPapi default)
    polymarket_us.py     v2 only — stub until §4.6 is verified
  data/
    tennis_data.py       tennis-data.co.uk loader (§4.7)
    sackmann.py          Sackmann CSV loader (§4.8)
  match/
    normalize.py         player-name normalization
    linker.py            Kalshi market ↔ odds fixture ↔ results row
  model/
    devig.py             multiplicative, power, shin
    elo.py               surface Elo (filter only)
  strategy/
    signal.py            edge computation
    quoting.py           maker price selection, requote logic
    sizing.py            fractional Kelly + caps
  exec/
    live.py              sends orders via kalshi.py
    paper.py             simulated fills (§10)
  risk/
    limits.py            pre-trade checks
    killswitch.py        cancel-all + lock file
    reconcile.py         positions vs. DB, every RECONCILE_INTERVAL_SEC
  db/
    schema.sql
    migrations/
  backtest/
    calibration.py       predicted vs realized by bucket
    replay.py            replays logged snapshots through strategy
    reports/             one markdown report per strategy change
  main.py                scheduler entrypoint
tests/
docker/
  Dockerfile
  docker-compose.yml     app + postgres
```

**Stack:** Python 3.11+, `httpx` (async REST), `websockets` (WS), `cryptography` (RSA-PSS signing), `pydantic` (schemas), `pandas`, `psycopg[binary]` + Postgres 16 (DuckDB acceptable for local backtests), `APScheduler`, `pytest` + `respx` (HTTP mocking), `rapidfuzz` (name matching), `unidecode`. Alerts via Discord webhook. No Kafka, no k8s, no ML frameworks in v1.

---

## 4. External APIs and data

### 4.1 Kalshi — environments [VERIFY]

| | REST base | WebSocket |
|---|---|---|
| Production | `https://api.elections.kalshi.com/trade-api/v2` (also `https://external-api.kalshi.com/trade-api/v2`) | `wss://api.elections.kalshi.com/trade-api/ws/v2` (also `wss://external-api-ws.kalshi.com/trade-api/ws/v2`) |
| Demo | `https://demo-api.kalshi.co/trade-api/v2` | `wss://demo-api.kalshi.co/trade-api/ws/v2` |

- Demo book is nearly empty → use **prod for reads**, demo only to test order flow/signing.
- Weekly exchange maintenance **3–5 AM ET**; trading paused. Scheduler must not send orders then.

### 4.2 Kalshi — authentication

Three headers on every signed request (and on the WS upgrade request):
```
KALSHI-ACCESS-KEY:       <key id>
KALSHI-ACCESS-TIMESTAMP: <unix time in MILLISECONDS, as string>
KALSHI-ACCESS-SIGNATURE: base64( RSA-PSS-SHA256( f"{timestamp}{METHOD}{path}" ) )
```
- `METHOD` upper-case. `path` starts with `/trade-api/v2/...`, **no host, no query string**. For WS sign `GET` + `/trade-api/ws/v2`.
- Padding: `PSS(mgf=MGF1(SHA256), salt_length=PSS.DIGEST_LENGTH)`, hash `SHA256`.
- Compute timestamp per request, not per session.
- Common 401 causes: seconds instead of ms, query string included in signed path, clock skew > ~5 s (run chrony/timesyncd on the server).
- Smallest signed sanity check: `GET /trade-api/v2/portfolio/balance` (balance is in cents).

Reference implementation:
```python
import base64, time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def load_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def signed_headers(key, key_id, method, path):
    ts = str(int(time.time() * 1000))
    sig = key.sign(
        f"{ts}{method.upper()}{path.split('?')[0]}".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {"KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode()}
```

### 4.3 Kalshi — rate limits [VERIFY]

- Roughly 10 req/s per API key (per key, not per IP). Default client throttle: 1 request / 100 ms.
- On 429: exponential backoff starting 500 ms, ×2, cap 30 s, ±20% jitter, honor `Retry-After` if present, max 6 retries then alert.
- Retry 5xx with the same backoff. Never retry other 4xx (except 409 duplicate `client_order_id` → treat as success and fetch the order).

### 4.4 Kalshi — endpoints used

Market data (public, no auth needed but sign anyway for simplicity):
| Purpose | Call |
|---|---|
| List tennis match markets | `GET /markets?series_ticker=KXATPMATCH&status=open` (and `KXWTAMATCH`); paginate with `cursor` |
| Market detail | `GET /markets/{ticker}` |
| Orderbook snapshot | `GET /markets/{ticker}/orderbook` |
| Trades | `GET /markets/trades?ticker=...` |
| Events | `GET /events/{event_ticker}` |

Portfolio (signed):
| Purpose | Call |
|---|---|
| Balance | `GET /portfolio/balance` |
| Positions | `GET /portfolio/positions` |
| Fills | `GET /portfolio/fills` (each fill reports actual `fee_cost`) |
| Create order | `POST /portfolio/orders` → 201 |
| Batch create | `POST /portfolio/orders/batched` |
| Amend | `POST /portfolio/orders/{order_id}/amend` |
| Decrease | `POST /portfolio/orders/{order_id}/decrease` |
| Cancel | `DELETE /portfolio/orders/{order_id}` |

**Series tickers (tennis)** — discover live via `GET /series` / `GET /markets` rather than trusting this list [VERIFY]:
- v1: `KXATPMATCH`, `KXWTAMATCH`
- Later: `KXATPCHALLENGERMATCH`, `KXWTACHALLENGERMATCH`, `KXATPDOUBLES`, `KXATPSETWINNER`, `KXATPGAMETOTAL`, `KXATPGAMESPREAD`, `KXATP`, `KXWTA`
- Example market ticker shape: `KXATPMATCH-26OCT09HALBLO` (series-date-player codes). Each match event has one market per player; YES on a market = that player wins.

### 4.5 Kalshi — order schema [VERIFY — schema is mid-migration]

Kalshi is moving from integer-cent fields (`count`, `yes_price`, `no_price`) to fixed-point string fields (`count_fp`, `yes_price_dollars`, `no_price_dollars`). Some reports say the old fields already return 400. **Check docs.kalshi.com before implementing; send one schema only.** Target shape:
```json
{
  "ticker": "KXATPMATCH-...",
  "action": "buy",
  "side": "yes",
  "count_fp": "10.00",
  "yes_price_dollars": "0.54",
  "time_in_force": "good_till_canceled",
  "post_only": true,
  "client_order_id": "tb-20261109-a1b2c3",
  "expiration_ts": 1762732800
}
```
- Prices valid 1¢–99¢.
- `client_order_id`: only `[A-Za-z0-9-]`. Never embed a ticker (some contain `.`).
- Set `expiration_ts` ≤ scheduled match start as a second safety net behind §1.2.
- YES/NO convention: orderbook returns YES bids and NO bids. Best YES ask = `1 − best NO bid`. Write one helper for this and test it.
- Useful extra fields: `self_trade_prevention_type`, `order_group_id` (cap total contracts across a group), `reduce_only`.

### 4.6 Kalshi WebSocket

- Connect with signed headers on the upgrade; `websockets.connect(url, additional_headers=..., ping_interval=20, ping_timeout=10)`. Kalshi drops idle connections after ~60 s without client activity.
- Subscribe:
```json
{"id": 1, "cmd": "subscribe",
 "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXATPMATCH-..."]}}
```
- Channels: public `ticker`, `trade`, `orderbook_delta`, `market_lifecycle_v2`; private `fill`, `user_orders`, `market_positions`.
- `orderbook_delta` sends `orderbook_snapshot` first, then deltas with a sequence number. **On a sequence gap or reconnect: drop local book, resubscribe, wait for new snapshot.** Kalshi does not replay missed frames.
- Reconnect loop with exponential backoff capped at 30 s.
- v1 may use REST polling (every 15–30 s per open market) instead of WS; WS is required only once maker requoting is live.

### 4.7 Kalshi fees [VERIFY at kalshi.com/fee-schedule]

```
taker_fee = ceil_to_cent(0.07   * C * P * (1 - P))
maker_fee = ceil_to_cent(0.0175 * C * P * (1 - P))   # only on series listed with maker fees; else 0
```
- P = price in dollars, C = contracts. Rounding is applied to the order total, so per-contract cost on small orders is higher than the formula (1 contract at 50¢ = 2¢, not 1.75¢).
- Most sports series currently charge no maker fee — confirm for `KXATPMATCH`/`KXWTAMATCH`.
- No fee to cancel or to settle. ACH free; debit card deposits charged.
- Accounting must use `fee_cost` from fills, not the estimate.

### 4.8 Odds provider — Pinnacle prices

Pinnacle closed its public API in July 2025; get Pinnacle via an aggregator. Default: **OddsPapi**.
- Base: `https://api.oddspapi.io/v4`, auth via `apiKey` query param.
- Tennis `sportId=12`.
- `GET /fixtures?sportId=12&from=YYYY-MM-DD&to=YYYY-MM-DD` (max 10-day window). `categoryName` gives tier (ATP/WTA/Challenger/ITF).
- `GET /odds?fixtureId=...` live odds (live response nests prices as dicts keyed `"0"`).
- `GET /historical-odds?fixtureId=...&bookmakers=pinnacle,kalshi,polymarket` (max 3 bookmakers per call; returns lists, not dicts). Closing price = last tick before start.
- Match-winner market id: blog posts disagree (`171` with outcomes 171/172 vs `121`) **[VERIFY by inspecting a live response]**.
- Free tier ≈ 250 requests/month — enough for backtests, **not** for live polling. Live trading needs a paid tier or a Pinnacle-only feed (e.g. pinnapi: free 100 req/day, paid ~$99–229/mo). Budget for this.
- On 429 honor the `retryMs` field.
- Wrap everything behind `odds.py` with this interface so the provider can be swapped:
```python
class OddsProvider(Protocol):
    async def list_fixtures(self, start: date, end: date) -> list[Fixture]: ...
    async def pinnacle_moneyline(self, fixture_id: str) -> Moneyline | None: ...   # decimal odds p1, p2, ts
    async def closing_moneyline(self, fixture_id: str) -> Moneyline | None: ...
```

### 4.9 Polymarket US (v2 only) [VERIFY everything]

- Separate CFTC-regulated exchange; keys from `polymarket.us/developer` after KYC. Keys do **not** work on polymarket.com.
- Reported auth: Ed25519 signature in headers `X-PM-Access-Key`, `X-PM-Timestamp`, `X-PM-Signature`; SDK `pip install polymarket-us`. Exchange API docs show bases `https://api.prod.polymarketexchange.com/v1` (prod), `api.preprod...`, `api.dev01...`, with access tokens expiring every 3 minutes. Sources disagree — read official docs first.
- Walkovers: resolve at last fair market price; ITF walkover $0.50.
- Leave `clients/polymarket_us.py` as a stub raising `NotImplementedError` until verified.

### 4.10 tennis-data.co.uk (backtest ground truth)

- Annual ATP and WTA files from `tennis-data.co.uk/alldata.php`. Download manually into `data/raw/tennis_data/` (scripted download is blocked by Cloudflare — verified Nov 2026).
- Manual download URLs: `https://www.tennis-data.co.uk/alldata.php?year=YYYY&file=atp` and `...&file=wta`, for each season. Page: https://www.tennis-data.co.uk/alldata.php
- Key columns: `Date`, `Tournament`, `Series`/`Tier`, `Court`, `Surface`, `Round`, `Best of`, `Winner`, `Loser`, `WRank`, `LRank`, `WPts`, `LPts`, `W1..W5`, `L1..L5`, `Wsets`, `Lsets`, `Comment` (Completed / Retired / Walkover), `PSW`/`PSL` (Pinnacle odds, winner/loser), `B365W`/`B365L`, `MaxW`/`MaxL`, `AvgW`/`AvgL`.
- Names are `"Lastname F."` format. Odds are closing-ish decimal odds.
- Rows are winner/loser, not p1/p2 → randomize orientation before modeling or every model looks perfect.
- Exclude `Comment != "Completed"` from calibration; keep them for settlement-rule tests.

### 4.11 Jeff Sackmann data (Elo features)

- GitHub `JeffSackmann/tennis_atp`, `tennis_wta`: `atp_matches_YYYY.csv`, `wta_matches_YYYY.csv`, `atp_players.csv` (`player_id, name_first, name_last, hand, dob, ioc`), rankings files.
- **UPDATE (Nov 2026):** both original repos now return 404. We use the archival mirror `github.com/Aneeshers/tennis-sackmann-archive` (`atp/`, `wta/` folders, snapshot of upstream June 2026, coverage through 2026). Same CC BY-NC-SA license. HF mirror: https://huggingface.co/datasets/Aneeshers/tennis-sackmann-archive
- Match columns: `tourney_id, tourney_name, surface, draw_size, tourney_level, tourney_date, match_num, winner_id, winner_name, loser_id, loser_name, score, best_of, round, minutes`, serve stats `w_ace, w_df, w_svpt, ...`, `winner_rank, loser_rank`.
- License CC BY-NC-SA — non-commercial use only. Keep that in mind if this ever makes money.

---

## 5. Event matching (the hardest part)

Every trade depends on correctly linking: Kalshi market ↔ odds fixture ↔ (later) result.

Normalization (`match/normalize.py`):
1. `unidecode`, lowercase, strip punctuation, collapse whitespace.
2. Hyphens → spaces (`auger-aliassime` ≡ `auger aliassime`).
3. Produce keys: `full`, `last`, `last_first_initial` (e.g. `sinner j`).
4. Maintain `data/player_aliases.csv` (`canonical_name, alias, source`) for known exceptions.

Linking (`match/linker.py`):
- Candidate pairs = same tour, start times within ±12 h.
- Score = best `rapidfuzz.token_sort_ratio` over the two players (order-independent) + tournament name similarity + time proximity.
- `confidence ≥ 0.95` → auto-link. `0.80–0.95` → store, flag, **do not trade**. Below → ignore.
- Store mapping in `match_links(kalshi_event_ticker, odds_fixture_id, confidence, method, created_at)`.
- Player orientation: explicitly map which Kalshi market (YES = player X) corresponds to odds outcome 1 vs 2. Unit-test with swapped orders.

---

## 6. Formulas

### 6.1 De-vig (two-way)
```python
def devig_multiplicative(o1, o2):
    r1, r2 = 1/o1, 1/o2
    return r1/(r1+r2), r2/(r1+r2)

def devig_power(o1, o2):
    # find k: (1/o1)**k + (1/o2)**k == 1, then p_i = (1/o_i)**k ; solve with brentq on k in (0.5, 2)

def devig_shin(o1, o2):
    # Shin's z-model; reduces to closed form for 2 outcomes
```
Default: **multiplicative**. Switch only if a backtest shows lower log-loss on tennis-data.co.uk Pinnacle odds over ≥ 2 seasons. Record overround `r1 + r2 - 1` with every snapshot.

### 6.2 Fee function
```python
import math
def kalshi_fee(price: float, contracts: int, maker: bool, maker_fee_series: bool) -> float:
    rate = 0.0175 if maker else 0.07
    if maker and not maker_fee_series:
        return 0.0
    return math.ceil(rate * contracts * price * (1 - price) * 100) / 100
```

### 6.3 Sizing
```python
kelly_f = (fair_p - price) / (1 - price)          # buying YES at `price`
stake   = KELLY_FRACTION * kelly_f * bankroll
contracts = floor(stake / price)
contracts = min(contracts, caps_from_risk_limits)
```
Skip if `contracts < 1`.

### 6.4 Closing-line value
```
clv_pinnacle = fair_p_at_close - entry_price          # in probability points
clv_venue    = venue_mid_at_close - entry_price
```
Close = last snapshot before scheduled start.

---

## 7. Settlement rules (read before any multi-venue logic)

- **Kalshi match winner:** ATP/WTA walkover → resolves at **last fair price**; ITF walkover → **$0.50**. **[VERIFY in the series' contract terms PDF]**
- **Kalshi set/score/game markets:** walkover → last fair price; retirement → contracts already decided settle normally, the rest at last fair price. Player replaced before start → may resolve at last fair price and a new contract is listed.
- **Polymarket US:** last fair market price; ITF walkover $0.50.
- **Pinnacle/books:** rules differ again (often "one set completed" rule). Irrelevant for settlement since we don't bet there, but it matters for interpreting historical odds on retirements.
- Store the contract-terms URL / rulebook id (e.g. `TENNISSETWINNER`) with every market row.
- Contract terms PDFs live at `https://kalshi-public-docs.s3.amazonaws.com/contract_terms/<RULEBOOK>.pdf`.

---

## 8. Database schema (Postgres)

```sql
CREATE TABLE players (
  player_id    SERIAL PRIMARY KEY,
  canonical    TEXT UNIQUE NOT NULL,
  sackmann_id  INT,
  tour         TEXT CHECK (tour IN ('ATP','WTA'))
);

CREATE TABLE matches (
  match_id          SERIAL PRIMARY KEY,
  tour              TEXT NOT NULL,
  tournament        TEXT,
  surface           TEXT,
  round             TEXT,
  p1_id             INT REFERENCES players,
  p2_id             INT REFERENCES players,
  scheduled_start   TIMESTAMPTZ,
  status            TEXT,      -- scheduled | live | completed | retired | walkover | cancelled
  winner_id         INT REFERENCES players
);

CREATE TABLE venue_markets (
  venue            TEXT NOT NULL,          -- kalshi | polymarket_us
  venue_ticker     TEXT NOT NULL,
  event_ticker     TEXT,
  match_id         INT REFERENCES matches,
  yes_player_id    INT REFERENCES players,
  rulebook         TEXT,
  close_time       TIMESTAMPTZ,
  PRIMARY KEY (venue, venue_ticker)
);

CREATE TABLE match_links (
  match_id          INT REFERENCES matches,
  odds_fixture_id   TEXT,
  confidence        REAL,
  method            TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE book_snapshots (          -- append-only, high volume
  ts            TIMESTAMPTZ NOT NULL,
  venue         TEXT NOT NULL,
  venue_ticker  TEXT NOT NULL,
  yes_bid_c     SMALLINT, yes_ask_c SMALLINT,
  yes_bid_sz    INT,      yes_ask_sz INT,
  last_c        SMALLINT, volume INT, open_interest INT
);
CREATE INDEX ON book_snapshots (venue_ticker, ts);

CREATE TABLE odds_snapshots (
  ts             TIMESTAMPTZ NOT NULL,
  match_id       INT REFERENCES matches,
  book           TEXT NOT NULL,          -- pinnacle | ...
  odds_p1        NUMERIC(8,3), odds_p2 NUMERIC(8,3),
  fair_p1        REAL,                   -- de-vigged
  overround      REAL,
  devig_method   TEXT
);

CREATE TABLE decisions (
  ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
  match_id      INT, venue_ticker TEXT, side TEXT,
  fair_p        REAL, price_c SMALLINT, fee_c SMALLINT, edge REAL,
  action        TEXT,          -- place | amend | cancel | skip
  reason        TEXT,          -- e.g. EDGE_TOO_SMALL, STALE_ODDS, LOW_MATCH_CONF, RISK_LIMIT, TOO_CLOSE_TO_START
  mode          TEXT           -- paper | live
);

CREATE TABLE orders (
  client_order_id TEXT PRIMARY KEY,
  venue_order_id  TEXT,
  venue_ticker    TEXT, side TEXT, action TEXT,
  price_c SMALLINT, count INT, post_only BOOL,
  status TEXT, mode TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ
);

CREATE TABLE fills (
  fill_id TEXT PRIMARY KEY, client_order_id TEXT REFERENCES orders,
  ts TIMESTAMPTZ, price_c SMALLINT, count INT, fee_cost_c INT, is_taker BOOL, mode TEXT
);

CREATE TABLE settlements (
  venue_ticker TEXT PRIMARY KEY, result TEXT, settle_price_c SMALLINT, ts TIMESTAMPTZ
);
```
Conventions: prices as integer cents (`_c`) in venue tables, probabilities as REAL in [0,1]; never mix in one column. All timestamps UTC.

---

## 9. Risk controls

`risk/limits.py` checks before every place/amend:
- `exposure_after_order(match) ≤ MAX_EXPOSURE_PER_MATCH`
- `exposure_today ≤ MAX_EXPOSURE_PER_DAY`
- `open_exposure_total ≤ MAX_TOTAL_EXPOSURE`
- `open_orders_count ≤ MAX_OPEN_ORDERS`
- `daily_realized_pnl ≥ -MAX_DAILY_LOSS`
- No more than one side (YES or NO) of the same match at once.

Exposure = max loss = `price × contracts` for buys (+ fees).

Kill switch triggers: any limit breach, reconciliation mismatch, 3 consecutive order errors, WS book desync not recovered within 60 s, clock skew > 2 s. Action: `DELETE` every resting order, write `/tmp/KILL` lock file, send alert, refuse new orders until the lock file is removed by a human.

Reconciliation every `RECONCILE_INTERVAL_SEC`: compare `GET /portfolio/positions` + resting orders to DB; any mismatch → kill switch.

---

## 10. Paper trading rules

- Same code path as live up to `exec/`; only the executor differs.
- **Taker paper fill:** fill at the current best opposite price for up to the displayed size; remainder unfilled.
- **Maker paper fill:** count as filled only when a logged trade prints at or through your price **after** your order time, and only up to that trade's size minus size that was ahead of you in the queue (assume you were last in queue at your price level). This is pessimistic on purpose.
- Fees computed with §6.2.
- Paper results are suspect if fill rate > 50% for maker orders; flag it.

---

## 11. Backtesting and evaluation

Stage A (no prediction-market data needed): `backtest/calibration.py`
- Using tennis-data.co.uk 2015–present, de-vig `PSW/PSL`, randomize orientation, bucket predicted prob into 5% bins, plot predicted vs realized, report Brier score and log-loss per de-vig method and per tour/surface.

Stage B (needs own Kalshi snapshots): `backtest/replay.py`
- Replay `book_snapshots` + `odds_snapshots` chronologically through `strategy/` with the paper executor.
- Report: number of trades, fill rate, mean edge at entry, mean CLV vs Pinnacle close, P&L after fees, max drawdown, P&L by price bucket (check longshot bias), by tour, by hours-to-start.

Go-live gate (all required):
- ≥ 200 paper trades over ≥ 4 weeks.
- Mean CLV vs Pinnacle close > 0 with 95% CI excluding 0.
- No unresolved reconciliation or matching errors in the last 2 weeks.

Every strategy change: new report in `backtest/reports/YYYY-MM-DD-<change>.md` with before/after metrics.

---

## 12. Scheduler jobs (`main.py`)

| Job | Interval | Notes |
|---|---|---|
| discover_markets | 10 min | list open `KXATPMATCH`/`KXWTAMATCH`, upsert `venue_markets` |
| discover_fixtures | 30 min | odds provider fixtures for next 48 h |
| link_events | after both discovery jobs | §5 |
| poll_kalshi_books | 15–30 s per active market (or WS) | → `book_snapshots` |
| poll_pinnacle | as budget allows; tighter near start | → `odds_snapshots` |
| strategy_tick | 15 s | signals → decisions → orders |
| pre_start_cancel | 10 s | cancel orders within `CANCEL_BEFORE_START_SEC` |
| reconcile | 60 s | §9 |
| settle | 15 min | record settlements, compute CLV + P&L |
| maintenance_guard | always | no orders 3–5 AM ET |

---

## 13. Config (`config.yaml`)

```yaml
MODE: paper                  # paper | live (live also needs env I_UNDERSTAND_LIVE_TRADING=yes)
VENUES: [kalshi]
SERIES: [KXATPMATCH, KXWTAMATCH]

# signal
DEVIG_METHOD: multiplicative
MIN_EDGE_MAKER: 0.015        # probability points after fees
MIN_EDGE_TAKER: 0.03
MIN_PRICE: 0.10
MAX_PRICE: 0.90
MAX_ODDS_AGE_SEC: 300
MIN_MATCH_CONFIDENCE: 0.95
MIN_TIME_TO_START_SEC: 600
MAX_TIME_TO_START_SEC: 86400
REQUOTE_THRESHOLD: 0.01
REQUOTE_INTERVAL_SEC: 60
CANCEL_BEFORE_START_SEC: 120

# sizing
BANKROLL_USD: 200
KELLY_FRACTION: 0.1

# risk
MAX_EXPOSURE_PER_MATCH: 20
MAX_EXPOSURE_PER_DAY: 80
MAX_TOTAL_EXPOSURE: 150
MAX_OPEN_ORDERS: 20
MAX_DAILY_LOSS: 40
RECONCILE_INTERVAL_SEC: 60

# infra
KALSHI_ENV: prod             # prod for reads; demo for order-flow tests
KALSHI_MIN_REQUEST_INTERVAL_MS: 100
```
All numeric values are starting placeholders; change only with a backtest report.

`.env.example`:
```
KALSHI_KEY_ID=
KALSHI_PRIVATE_KEY_PATH=
ODDS_API_KEY=
DATABASE_URL=postgresql://bot:bot@localhost:5432/tennis
DISCORD_WEBHOOK_URL=
I_UNDERSTAND_LIVE_TRADING=no
```

---

## 14. Testing requirements

- All network calls mocked (`respx`); no test may hit a real API.
- Required unit tests: signing string (ms timestamp, no query string), YES/NO price conversion, fee rounding, each de-vig method on known inputs, name normalization incl. diacritics and hyphens, player orientation in linking, risk limit rejections, kill switch cancels everything, `client_order_id` charset.
- Required integration test: full paper loop on a recorded fixture of snapshots produces deterministic decisions.
- `pytest -q` must pass before any commit.

---

## 15. Phases and definition of done

1. **Data** — loaders for tennis-data.co.uk + Sackmann; calibration report (Stage A) committed. Kalshi + odds snapshot logger running continuously.
2. **Fair value + matching** — de-vig, linker with ≥ 99% correct links on a hand-checked sample of 200 matches.
3. **Paper** — full loop in `MODE=paper` for ≥ 4 weeks; Stage B report.
4. **Live small** — passes go-live gate (§11); tiny limits; demo-env order-flow test first; daily reconciliation report.
5. **Later** — WS maker requoting, Polymarket US, Challenger, set/game markets via a point-by-point Markov model.

Do not start a phase until the previous phase's definition of done is met.

---

## 16. Known pitfalls

- Clock skew silently breaks Kalshi auth.
- Winner/loser-oriented historical data leaks the label.
- Snapshot only every 30 min is too coarse to measure lag edge; aim ≤ 30 s near start.
- Kalshi tennis prices move point-by-point once live — anything still resting at start is likely to be picked off.
- Kalshi may list a new contract if a player is replaced; old one may settle at last fair price. Treat replacements as new matches.
- Free odds tiers will exhaust within days if polled live; track request budget in metrics.
- Low-priced contracts are systematically overpriced; a strategy that mostly buys < 20¢ YES is probably wrong.
- Polymarket international (polymarket.com) blocks US persons — never integrate it.

---

## 17. Sources

- Kalshi docs: https://docs.kalshi.com (auth quick start, create order, WebSockets, fee schedule at https://kalshi.com/fee-schedule)
- Kalshi tennis series list: https://kalshi.com/tennis/predictions
- Kalshi contract terms: https://kalshi-public-docs.s3.amazonaws.com/contract_terms/
- Bürgi, Deng & Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market": https://cepr.org/voxeu/columns/economics-kalshi-prediction-market
- OddsPapi tennis docs/blog: https://oddspapi.io/blog/?p=2938
- Polymarket US API: https://apidocs.polymarketexchange.com/api-reference
- tennis-data.co.uk: https://www.tennis-data.co.uk/alldata.php (manual download only — Cloudflare blocks scripts)
- Sackmann data (original, now 404): https://github.com/JeffSackmann/tennis_atp · https://github.com/JeffSackmann/tennis_wta
- Sackmann archive mirror (in use): https://github.com/Aneeshers/tennis-sackmann-archive · https://huggingface.co/datasets/Aneeshers/tennis-sackmann-archive
