"""Odds provider adapter (OddsPapi default). See AGENTS.md §4.8.

Pinnacle closed its public API in July 2025; all Pinnacle prices come via an
aggregator. Wrap everything behind OddsProvider so the provider can be swapped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass
class Fixture:
    fixture_id: str
    sport: str
    category: str | None
    start_time: datetime | None
    p1_name: str | None = None
    p2_name: str | None = None
    tournament: str | None = None


@dataclass
class Moneyline:
    odds_p1: float  # decimal odds
    odds_p2: float
    ts: datetime


class OddsProvider(Protocol):
    async def list_fixtures(self, start: date, end: date) -> list[Fixture]: ...
    async def pinnacle_moneyline(self, fixture_id: str) -> Moneyline | None: ...
    async def closing_moneyline(self, fixture_id: str) -> Moneyline | None: ...


class OddsPapiClient:
    """TODO: OddsPapi v4 client (https://api.oddspapi.io/v4, apiKey query param,
    sportId=12 for tennis, honor `retryMs` on 429).

    Endpoints: GET /fixtures, GET /odds, GET /historical-odds (max 3 bookmakers).
    Free tier ~250 req/month — track request budget. See AGENTS.md §4.8 for the
    match-winner market-id verification task."""

    BASE = "https://api.oddspapi.io/v4"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.requests_used = 0

    async def list_fixtures(self, start: date, end: date) -> list[Fixture]:
        raise NotImplementedError

    async def pinnacle_moneyline(self, fixture_id: str) -> Moneyline | None:
        raise NotImplementedError

    async def closing_moneyline(self, fixture_id: str) -> Moneyline | None:
        raise NotImplementedError
