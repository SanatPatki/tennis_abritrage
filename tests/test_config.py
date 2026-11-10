"""Settings/env loading tests — the live-trading gate is critical (§1.1)."""

import pytest

from src.config import Settings


def test_defaults_to_paper(monkeypatch, tmp_path):
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.delenv("I_UNDERSTAND_LIVE_TRADING", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("MODE: paper\n")
    s = Settings.load(str(cfg), str(tmp_path / "nonexistent.env"))
    assert s.mode == "paper"
    assert not s.live_allowed


def test_live_requires_both_flags(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("MODE: live\n")
    env = tmp_path / ".env"
    # mode=live but no ack -> still not allowed
    env.write_text("I_UNDERSTAND_LIVE_TRADING=no\n")
    s = Settings.load(str(cfg), str(env))
    assert s.mode == "live" and not s.live_allowed
    # both set -> allowed (clear var first: load_dotenv won't override)
    env.write_text("I_UNDERSTAND_LIVE_TRADING=yes\n")
    monkeypatch.delenv("I_UNDERSTAND_LIVE_TRADING", raising=False)
    s2 = Settings.load(str(cfg), str(env))
    assert s2.live_allowed


def test_kalshi_env_selects_base_url(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("KALSHI_ENV: demo\n")
    s = Settings.load(str(cfg), str(tmp_path / "none.env"))
    assert "demo-api" in s.kalshi_base_url
    cfg.write_text("KALSHI_ENV: prod\n")
    assert "api.elections" in Settings.load(str(cfg), str(tmp_path / "none.env")).kalshi_base_url


def test_missing_key_raises_actionable(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("{}\n")
    s = Settings.load(str(cfg), str(tmp_path / "none.env"))
    with pytest.raises(RuntimeError, match="KALSHI_KEY_ID"):
        s.require_kalshi_auth()
