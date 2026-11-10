"""Environment + secrets loading. See AGENTS.md §1.5, §4.2, §13.

Secrets come ONLY from env vars / .env — never from config.yaml, never logged.
Live trading requires MODE=live AND I_UNDERSTAND_LIVE_TRADING=yes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .clients.kalshi import DEMO_REST, PROD_REST, KalshiClient, load_key


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v not in ("", None) else None


@dataclass
class Settings:
    """Runtime settings: config.yaml values + env secrets."""

    mode: str = "paper"                    # paper | live
    venues: list[str] = field(default_factory=lambda: ["kalshi"])
    series: list[str] = field(default_factory=lambda: ["KXATPMATCH", "KXWTAMATCH"])
    kalshi_env: str = "prod"               # prod | demo
    database_url: str | None = None
    discord_webhook_url: str | None = None
    odds_api_key: str | None = None
    kalshi_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    live_trading_ack: bool = False
    raw: dict = field(default_factory=dict)  # full config.yaml for strategy params

    @classmethod
    def load(cls, config_path: str = "config.yaml", env_path: str = ".env") -> "Settings":
        load_dotenv(env_path)
        raw: dict = {}
        if Path(config_path).exists():
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}
        return cls(
            mode=str(raw.get("MODE", "paper")).lower(),
            venues=list(raw.get("VENUES", ["kalshi"])),
            series=list(raw.get("SERIES", ["KXATPMATCH", "KXWTAMATCH"])),
            kalshi_env=str(raw.get("KALSHI_ENV", "prod")).lower(),
            database_url=_env("DATABASE_URL"),
            discord_webhook_url=_env("DISCORD_WEBHOOK_URL"),
            odds_api_key=_env("ODDS_API_KEY"),
            kalshi_key_id=_env("KALSHI_KEY_ID"),
            kalshi_private_key_path=_env("KALSHI_PRIVATE_KEY_PATH"),
            live_trading_ack=_env("I_UNDERSTAND_LIVE_TRADING") == "yes",
            raw=raw,
        )

    # -- derived ---------------------------------------------------------

    @property
    def kalshi_base_url(self) -> str:
        return DEMO_REST if self.kalshi_env == "demo" else PROD_REST

    @property
    def live_allowed(self) -> bool:
        """AGENTS.md §1.1: live needs BOTH the config mode and the env ack."""
        return self.mode == "live" and self.live_trading_ack

    def require_kalshi_auth(self) -> tuple[str, str]:
        """Return (key_id, key_path); raise with actionable message if missing."""
        if not self.kalshi_key_id:
            raise RuntimeError("KALSHI_KEY_ID is not set — see .env.example")
        if not self.kalshi_private_key_path:
            raise RuntimeError("KALSHI_PRIVATE_KEY_PATH is not set — see .env.example")
        if not Path(self.kalshi_private_key_path).exists():
            raise RuntimeError(
                f"Kalshi private key not found at {self.kalshi_private_key_path} "
                "(keep .pem files OUTSIDE the repo)"
            )
        return self.kalshi_key_id, self.kalshi_private_key_path

    def get_kalshi_client(self) -> KalshiClient:
        """Build an authenticated Kalshi REST client for the configured env."""
        key_id, key_path = self.require_kalshi_auth()
        return KalshiClient(self.kalshi_base_url, load_key(key_path), key_id)

    def check(self) -> list[str]:
        """Return list of config problems; empty means ready to run."""
        problems = []
        if self.mode == "live" and not self.live_trading_ack:
            problems.append(
                "MODE=live but I_UNDERSTAND_LIVE_TRADING!=yes — live orders refused"
            )
        try:
            self.require_kalshi_auth()
        except RuntimeError as e:
            problems.append(str(e))
        if not self.database_url:
            problems.append("DATABASE_URL is not set")
        if not self.odds_api_key:
            problems.append("ODDS_API_KEY is not set (needed for Pinnacle prices)")
        return problems


if __name__ == "__main__":
    # `python -m src.config` — env sanity check, prints problems only
    s = Settings.load()
    problems = s.check()
    if problems:
        print("CONFIG PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    else:
        print(f"config OK: MODE={s.mode} KALSHI_ENV={s.kalshi_env} base={s.kalshi_base_url}")
