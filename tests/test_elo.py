"""Surface Elo tests."""

import pandas as pd

from src.model.elo import ALL_SURFACE, DEFAULT_RATING, SurfaceElo


def test_favorite_wins_more_often():
    elo = SurfaceElo(k_factor=32.0)
    # player 1 beats player 2 ten times on hard
    for _ in range(10):
        elo.update_match(1, 2, "Hard")
    p = elo.win_prob(1, 2, "Hard")
    assert p > 0.5
    # and the margin grows with more wins
    for _ in range(10):
        elo.update_match(1, 2, "Hard")
    assert elo.win_prob(1, 2, "Hard") > p


def test_surface_ratings_are_separate():
    elo = SurfaceElo()
    elo.update_match(1, 2, "Clay")
    # clay rating moved; grass untouched
    assert elo.rating(1, "clay") != DEFAULT_RATING
    assert elo.rating(1, "grass") == DEFAULT_RATING
    # but ALL-surface rating moved for both
    assert elo.rating(1, ALL_SURFACE) != DEFAULT_RATING
    assert elo.rating(2, ALL_SURFACE) != DEFAULT_RATING


def test_fit_is_chronological():
    df = pd.DataFrame(
        {
            "winner_id": [1, 2, 1],
            "loser_id": [2, 1, 3],
            "surface": ["Hard", "Hard", "Clay"],
            "tourney_date": [20240101, 20240201, 20240301],
        }
    )
    elo = SurfaceElo().fit(df)
    # player 1: 2 wins (hard, clay), 1 loss (hard)
    assert elo.matches_played[(1, "hard")] == 2
    assert elo.matches_played[(1, "clay")] == 1
    assert elo.rating(1) > DEFAULT_RATING  # net positive


def test_unknown_players_default_to_even():
    elo = SurfaceElo()
    assert elo.win_prob(999, 998, "Hard") == 0.5
