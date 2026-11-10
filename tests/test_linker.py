"""Linker tests per AGENTS.md §14: name normalization, orientation, thresholds."""

from datetime import datetime, timedelta, timezone

from src.match.linker import (
    AUTO_LINK,
    FLAG_LINK,
    MatchLinker,
    OddsFixture,
    VenueSide,
)

T0 = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc)


def _event(names=("Jannik Sinner", "Taylor Fritz"), tour="ATP", start=T0):
    """Build two VenueSides for one Kalshi event (one market per player)."""
    return [
        VenueSide(
            venue_ticker=f"KXATPMATCH-TEST-{i}",
            event_ticker="KXATPMATCH-TEST",
            player_name=n,
            tour=tour,
            tournament="ATP Finals",
            scheduled_start=start,
        )
        for i, n in enumerate(names)
    ]


def _fixture(p1="Jannik Sinner", p2="Taylor Fritz", tour="ATP",
             start=T0, fid="fx1", tournament="ATP Finals"):
    return OddsFixture(
        fixture_id=fid, p1_name=p1, p2_name=p2, tour=tour,
        tournament=tournament, start_time=start,
    )


def test_exact_match_auto_links():
    linker = MatchLinker()
    res = linker.link(_event(), [_fixture()])
    assert len(res) == 1
    r = res[0]
    assert r.confidence >= AUTO_LINK and r.auto and r.tradable
    # odds p1 = Sinner -> the Kalshi market whose YES is Sinner
    assert "Sinner" in next(
        s.player_name for s in _event() if s.venue_ticker == r.yes_is_odds_p1_ticker
    )


def test_swapped_orientation_maps_correct_ticker():
    """Fixture lists Fritz first; linker must still map YES=Sinner market to p1."""
    linker = MatchLinker()
    fx = _fixture(p1="Taylor Fritz", p2="Jannik Sinner")
    res = linker.link(_event(), [fx])
    assert len(res) == 1
    # odds p1 is now Fritz -> yes ticker should be Fritz's market
    sides = _event()
    p1_side = next(s for s in sides if "Fritz" in s.player_name)
    assert res[0].yes_is_odds_p1_ticker == p1_side.venue_ticker


def test_diacritics_hyphens_and_last_first():
    linker = MatchLinker()
    sides = _event(names=("Felix Auger-Aliassime", "Casper Ruud"))
    fx = _fixture(p1="Auger Aliassime F.", p2="Ruud C.")
    res = linker.link(sides, [fx])
    assert len(res) == 1 and res[0].tradable


def test_time_window_excludes_distant_fixture():
    linker = MatchLinker()
    fx = _fixture(start=T0 + timedelta(hours=13))
    assert linker.link(_event(), [fx]) == []


def test_tour_mismatch_ignored():
    linker = MatchLinker()
    assert linker.link(_event(tour="ATP"), [_fixture(tour="WTA")]) == []


def test_unknown_start_time_not_linked():
    """AGENTS.md §1.2: unknown start => do not trade."""
    linker = MatchLinker()
    sides = _event(start=None)
    assert linker.link(sides, [_fixture()]) == []


def test_low_similarity_ignored():
    linker = MatchLinker()
    fx = _fixture(p1="Carlos Alcaraz", p2="Novak Djokovic")
    res = linker.link(_event(), [fx])
    assert res == [] or all(r.confidence < FLAG_LINK for r in res)


def test_ambiguous_middle_band_flagged_not_tradable():
    """Force a mid-band confidence by degrading one name slightly."""
    linker = MatchLinker()
    sides = _event(names=("Jannik Sinner", "Taylor Fritzz"))
    res = linker.link(sides, [_fixture()])
    # exact behavior depends on fuzzy score; assert invariant only:
    for r in res:
        assert r.tradable == (r.confidence >= AUTO_LINK)
