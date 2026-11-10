"""Smoke tests for scaffolded pure functions. AGENTS.md §14 requires more
tests before any commit that touches real logic."""

import pytest

from src.clients.kalshi import kalshi_fee
from src.match.normalize import name_keys, normalize
from src.model.devig import devig_multiplicative, devig_power
from src.strategy.sizing import kelly_contracts


def test_normalize_diacritics_and_hyphens():
    assert normalize("Auger-Aliassime F.") == "auger aliassime f"
    # "First Last" order: last_first_initial -> "sinner j"
    assert name_keys("Jannik Sinner")["last_first_initial"] == "sinner j"
    # "Lastname F." order (tennis-data.co.uk) needs orientation handling in linker
    assert name_keys("Sinner J.")["full"] == "sinner j"


def test_devig_multiplicative_sums_to_one():
    p1, p2 = devig_multiplicative(1.8, 2.1)
    assert p1 + p2 == pytest.approx(1.0)
    assert p1 == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.1))


def test_devig_power_sums_to_one():
    p1, p2 = devig_power(1.8, 2.1)
    assert p1 + p2 == pytest.approx(1.0)


def test_kalshi_fee_rounding():
    # 1 contract at 50c taker: ceil(0.07*1*0.5*0.5*100)/100 = ceil(1.75)/100 = 0.02
    assert kalshi_fee(0.5, 1, maker=False, maker_fee_series=False) == pytest.approx(0.02)
    # maker with no maker-fee series -> 0
    assert kalshi_fee(0.5, 10, maker=True, maker_fee_series=False) == 0.0
    # maker with maker-fee series: ceil(0.0175*10*0.25*100)/100 = ceil(4.375)/100 = 0.05
    assert kalshi_fee(0.5, 10, maker=True, maker_fee_series=True) == pytest.approx(0.05)


def test_signed_headers_shape():
    # can't sign without a real key; just verify timestamp format via monkeypatch-free path
    pytest.skip("needs a test PEM fixture — see AGENTS.md §14")


def test_kelly_contracts():
    # fair 0.6, price 0.5, bankroll 200, fraction 0.1
    # kelly_f = 0.1/0.5 = 0.2; stake = 0.1*0.2*200 = 4; contracts = floor(4/0.5)=8
    assert kelly_contracts(0.6, 0.5, 200, 0.1, 100) == 8
    assert kelly_contracts(0.4, 0.5, 200, 0.1, 100) == 0
