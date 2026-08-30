"""The season-to-date record.

This is the live scoreboard, not the historical evaluation. It answers "how is
it doing right now", so the things worth pinning down are that the running
totals are honest and that the losses are actually shown.
"""

from __future__ import annotations

import datetime as dt

from fozzys_puckline.params import ModelParams
from fozzys_puckline.publish import build_season_track, run_models, tracked_season
from fozzys_puckline.schemas import Game

SEASON = 20232024


def _game(
    gid: int,
    day: int,
    *,
    season: int = SEASON,
    home_score: int = 3,
    away_score: int = 2,
    home_id: int = 10,
    away_id: int = 8,
    game_type: int = 2,
    final: bool = True,
) -> Game:
    return Game(
        game_id=gid,
        season=season,
        game_type=game_type,
        date_et=dt.date(2024, 1, 1) + dt.timedelta(days=day),
        home_id=home_id,
        away_id=away_id,
        home_abbrev="TOR",
        away_abbrev="MTL",
        home_score=home_score if final else None,
        away_score=away_score if final else None,
        last_period="REG" if final else None,
        state="FINAL" if final else "FUT",
    )


def _track(games: list[Game], season: int = SEASON):
    run = run_models(games, ModelParams())
    return build_season_track(run, games, season, dt.datetime(2024, 3, 1, tzinfo=dt.UTC), "test")


# -- which season ----------------------------------------------------------


def test_tracked_season_follows_the_latest_played_season() -> None:
    """It has to roll over on its own the first night of a new season."""
    games = [_game(1, 1, season=20222023), _game(2, 2, season=20232024)]
    assert tracked_season(games) == 20232024


def test_a_scheduled_season_does_not_become_the_tracked_one() -> None:
    """Next season's fixtures exist all summer; none of them are played."""
    games = [_game(1, 1, season=20232024), _game(2, 2, season=20242025, final=False)]
    assert tracked_season(games) == 20232024


def test_no_finished_games_means_nothing_to_track() -> None:
    assert tracked_season([_game(1, 1, final=False)]) is None


# -- the running record ----------------------------------------------------


def test_one_point_per_game_day() -> None:
    games = [_game(1, 1), _game(2, 1), _game(3, 5)]
    track = _track(games)
    assert [p.date for p in track.points] == [dt.date(2024, 1, 2), dt.date(2024, 1, 6)]
    assert [p.games_today for p in track.points] == [2, 1]


def test_cumulative_totals_only_ever_grow() -> None:
    track = _track([_game(i, i) for i in range(12)])
    games = [p.games for p in track.points]
    correct = [p.correct for p in track.points]
    assert games == sorted(games)
    assert correct == sorted(correct)


def test_the_last_point_is_the_season_summary() -> None:
    games = [_game(i, i) for i in range(10)]
    track = _track(games)
    assert track.summary is not None
    assert track.summary == track.points[-1]
    assert track.summary.games == len(games)


def test_playoffs_are_not_in_the_regular_season_record() -> None:
    games = [_game(1, 1), _game(2, 2, game_type=3)]
    track = _track(games)
    assert track.summary is not None
    assert track.summary.games == 1


def test_another_season_is_not_counted() -> None:
    games = [_game(1, 1, season=20222023), _game(2, 2)]
    track = _track(games, SEASON)
    assert track.summary is not None
    assert track.summary.games == 1


def test_the_rolling_window_is_empty_until_it_fills() -> None:
    """Reporting a 100-game trailing number off 12 games would be a lie."""
    track = _track([_game(i, i) for i in range(12)])
    assert all(p.rolling_accuracy is None for p in track.points)
    assert track.rolling_window == 100


def test_an_unfinished_season_is_marked_in_progress() -> None:
    games = [_game(i, i) for i in range(5)] + [_game(99, 40, final=False)]
    assert _track(games).complete is False


def test_no_games_yet_yields_an_empty_but_valid_track() -> None:
    track = _track([_game(1, 1, final=False)])
    assert track.summary is None
    assert track.points == []
    assert track.through is None


# -- the losses ------------------------------------------------------------


def test_biggest_misses_only_contains_actual_misses() -> None:
    """A game where the model had the winner ahead is not a miss."""
    games = [_game(i, i, home_score=3, away_score=2) for i in range(10)]
    track = _track(games)
    assert all(m.probability_given_to_winner < 0.5 for m in track.biggest_misses)


def test_misses_are_ordered_most_confident_first() -> None:
    games = [
        _game(i, i, home_score=0, away_score=4 if i % 2 else 1, home_id=10, away_id=8)
        for i in range(20)
    ]
    track = _track(games)
    given = [m.probability_given_to_winner for m in track.biggest_misses]
    assert given == sorted(given)


def test_a_miss_names_both_clubs_and_the_score() -> None:
    games = [_game(i, i, home_score=6, away_score=0) for i in range(12)]
    games.append(_game(99, 20, home_score=0, away_score=5))
    track = _track(games)

    assert track.biggest_misses
    worst = track.biggest_misses[0]
    assert worst.winner == "MTL"
    assert worst.loser == "TOR"
    assert worst.score == "5-0"


def test_an_overtime_result_says_so() -> None:
    games = [_game(i, i, home_score=6, away_score=0) for i in range(12)]
    upset = _game(99, 20, home_score=2, away_score=3)
    games.append(upset.model_copy(update={"last_period": "OT"}))

    track = _track(games)

    assert track.biggest_misses[0].score.endswith("OT")


def test_calibration_is_reported_with_its_own_threshold() -> None:
    track = _track([_game(i, i) for i in range(40)])
    assert track.calibration_threshold > 0
    assert isinstance(track.well_calibrated, bool)
