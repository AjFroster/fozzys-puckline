"""Direct estimation of the goal-model constants."""

from __future__ import annotations

import datetime as dt

import pytest

from fozzys_puckline.calibrate import calibrate, observed_tie_rate
from fozzys_puckline.schemas import Game


def _game(gid: int, season: int, home: int, away: int, last: str = "REG") -> Game:
    return Game(
        game_id=gid,
        season=season,
        game_type=2,
        date_et=dt.date(2024, 1, 1) + dt.timedelta(days=gid),
        home_id=10,
        away_id=8,
        home_abbrev="TOR",
        away_abbrev="MTL",
        home_score=home,
        away_score=away,
        last_period=last,  # type: ignore[arg-type]
        state="FINAL",
    )


def _corpus(season: int = 20232024, n: int = 400) -> list[Game]:
    games: list[Game] = []
    for i in range(n):
        if i % 5 == 0:
            games.append(_game(i, season, 3, 2, "OT"))  # regulation 2-2
        else:
            games.append(_game(i, season, 3 + i % 2, 2))
    return games


def test_calibrate_reports_the_seasons_it_used() -> None:
    constants = calibrate(_corpus(), [20232024])
    assert constants.seasons == (20232024,)
    assert constants.games == 400


def test_home_share_exceeds_one_half_when_the_home_team_scores_more() -> None:
    assert calibrate(_corpus(), [20232024]).home_share > 0.5


def test_calibrate_ignores_seasons_outside_the_window() -> None:
    """The holdout must never reach an estimator, or it stops measuring anything."""
    games = _corpus(20222023) + _corpus(20232024)
    assert calibrate(games, [20222023]).games == 400


def test_calibrate_rejects_an_empty_window() -> None:
    with pytest.raises(ValueError, match="no finished"):
        calibrate(_corpus(), [19992000])


def test_observed_tie_rate_counts_games_past_regulation() -> None:
    assert observed_tie_rate(_corpus(), [20232024]) == pytest.approx(0.2)


def test_playoff_games_are_excluded() -> None:
    playoff = _game(9999, 20232024, 4, 1)
    games = [*_corpus(), playoff.model_copy(update={"game_type": 3})]
    assert calibrate(games, [20232024]).games == 400
