"""What counts toward the score, and what only warms up the ratings."""

from __future__ import annotations

import datetime as dt

from fozzys_puckline.backtest import is_scorable
from fozzys_puckline.elo import GamePrediction


def _prediction(**overrides: object) -> GamePrediction:
    base: dict[str, object] = {
        "game_id": 1,
        "season": 20232024,
        "game_type": 2,
        "date_et": dt.date(2024, 1, 15),
        "home_abbrev": "TOR",
        "away_abbrev": "MTL",
        "home_elo_pre": 1500.0,
        "away_elo_pre": 1500.0,
        "hfa_applied": 35.0,
        "home_b2b": False,
        "away_b2b": False,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "home_win_prob": 0.55,
        "home_won": True,
        "no_fans": False,
        "neutral_site": False,
    }
    base.update(overrides)
    return GamePrediction(**base)  # type: ignore[arg-type]


def test_a_normal_final_counts() -> None:
    assert is_scorable(_prediction(), None, True)


def test_an_undecided_game_never_counts() -> None:
    assert not is_scorable(_prediction(home_won=None), None, True)


def test_playoffs_warm_ratings_but_are_not_scored() -> None:
    """Short series against a narrow set of opponents are not a fair sample."""
    assert not is_scorable(_prediction(game_type=3), None, True)


def test_seasons_outside_the_window_are_skipped() -> None:
    assert not is_scorable(_prediction(season=20222023), [20232024], True)
    assert is_scorable(_prediction(season=20232024), [20232024], True)


def test_empty_building_games_are_excluded_by_default() -> None:
    assert not is_scorable(_prediction(no_fans=True), None, True)
    assert not is_scorable(_prediction(neutral_site=True), None, True)


def test_they_can_be_opted_back_in() -> None:
    assert is_scorable(_prediction(no_fans=True), None, False)
