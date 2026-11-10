-- Schema per AGENTS.md §8. Postgres 16. Prices as integer cents (_c) in venue
-- tables, probabilities as REAL in [0,1]; never mix. All timestamps UTC.

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
