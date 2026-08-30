"""Rating engine behaviour."""

from __future__ import annotations

import datetime as dt

import pytest

from fozzys_puckline.elo import EloEngine, expected_score, mov_multiplier
from fozzys_puckline.params import BASE_RATING, EloParams
from fozzys_puckline.schemas import Game


def make_game(
    game_id: int = 1,
    *,
    season: int = 20232024,
    date: dt.date | None = None,
    home_id: int = 10,
    away_id: int = 8,
    home_score: int | None = 3,
    away_score: int | None = 2,
    last_period: str = "REG",
    state: str = "FINAL",
    **extra: object,
) -> Game:
    return Game(
        game_id=game_id,
        season=season,
        game_type=2,
        date_et=date or dt.date(2024, 1, 15),
        home_id=home_id,
        away_id=away_id,
        home_abbrev="TOR",
        away_abbrev="MTL",
        home_score=home_score,
        away_score=away_score,
        last_period=last_period,  # type: ignore[arg-type]
        state=state,  # type: ignore[arg-type]
        **extra,  # type: ignore[arg-type]
    )


# -- pure functions ---------------------------------------------------------


def test_equal_ratings_are_a_coin_flip() -> None:
    assert expected_score(0.0) == pytest.approx(0.5)


def test_expectation_is_symmetric() -> None:
    assert expected_score(100.0) + expected_score(-100.0) == pytest.approx(1.0)


def test_four_hundred_points_is_ten_to_one() -> None:
    assert expected_score(400.0) == pytest.approx(10 / 11, abs=1e-9)


def test_mov_multiplier_grows_with_margin() -> None:
    one = mov_multiplier(1, 0.0, 2.05)
    five = mov_multiplier(5, 0.0, 2.05)
    assert five > one > 0


def test_mov_multiplier_damps_the_favourite() -> None:
    """A heavy favourite winning big should move less than an even team doing so."""
    even = mov_multiplier(4, 0.0, 2.05)
    favourite = mov_multiplier(4, 300.0, 2.05)
    assert favourite < even


# -- updates ----------------------------------------------------------------


def test_update_is_zero_sum() -> None:
    engine = EloEngine()
    game = make_game()
    prediction = engine.predict(game)  # seeds both teams
    before = sum(engine.ratings.values())
    engine.observe(game, prediction)
    assert sum(engine.ratings.values()) == pytest.approx(before, abs=1e-9)


def test_home_win_raises_home_rating() -> None:
    engine = EloEngine()
    game = make_game(home_score=4, away_score=1)
    engine.observe(game, engine.predict(game))
    assert engine.rating(10) > BASE_RATING
    assert engine.rating(8) < BASE_RATING


def test_overtime_win_moves_less_than_a_regulation_win() -> None:
    """A 3-on-3 or shootout is near a coin flip; full credit would be a lie."""
    reg = EloEngine()
    reg_game = make_game(home_score=3, away_score=2, last_period="REG")
    reg.observe(reg_game, reg.predict(reg_game))

    ot = EloEngine()
    ot_game = make_game(home_score=3, away_score=2, last_period="OT")
    ot.observe(ot_game, ot.predict(ot_game))

    assert ot.rating(10) < reg.rating(10)
    assert ot.rating(10) > BASE_RATING


def test_unfinished_game_never_moves_ratings() -> None:
    engine = EloEngine()
    game = make_game(home_score=None, away_score=None, state="FUT", last_period="REG")
    engine.observe(game, engine.predict(game))
    assert engine.rating(10) == BASE_RATING


# -- pregame adjustments ----------------------------------------------------


def test_home_ice_favours_the_home_team() -> None:
    engine = EloEngine()
    assert engine.predict(make_game()).home_win_prob > 0.5


def test_neutral_site_removes_home_ice() -> None:
    engine = EloEngine()
    prediction = engine.predict(make_game(neutral_site=True))
    assert prediction.hfa_applied == 0.0
    assert prediction.home_win_prob == pytest.approx(0.5)


def test_empty_building_reduces_but_keeps_home_ice() -> None:
    """Measured at roughly half the edge, not none of it."""
    engine = EloEngine()
    normal = engine.predict(make_game()).hfa_applied
    empty = engine.predict(make_game(no_fans=True)).hfa_applied
    assert 0.0 < empty < normal


def test_back_to_back_is_detected_and_penalised() -> None:
    engine = EloEngine()
    first = make_game(game_id=1, date=dt.date(2024, 1, 15))
    engine.observe(first, engine.predict(first))

    second = make_game(game_id=2, date=dt.date(2024, 1, 16), away_id=9)
    prediction = engine.predict(second)

    assert prediction.home_b2b
    assert prediction.home_rest_days == 1
    assert not prediction.away_b2b


def test_fatigue_never_touches_the_stored_rating() -> None:
    """A tired team is temporarily worse, not permanently worse."""
    engine = EloEngine()
    first = make_game(game_id=1, date=dt.date(2024, 1, 15))
    engine.observe(first, engine.predict(first))
    rating_after_first = engine.rating(10)

    engine.predict(make_game(game_id=2, date=dt.date(2024, 1, 16)))

    assert engine.rating(10) == rating_after_first


# -- season boundaries ------------------------------------------------------


def test_season_rollover_regresses_toward_the_mean() -> None:
    engine = EloEngine(params=EloParams(carryover=0.5))
    engine.ratings = {10: 1600.0, 8: 1400.0}
    engine._season = 20232024

    engine._roll_season(20242025)

    assert engine.ratings[10] == pytest.approx(1550.0)
    assert engine.ratings[8] == pytest.approx(1450.0)


def test_rollover_conserves_total_rating() -> None:
    """Regressing to the league mean rather than a fixed 1500 is what stops the
    pool from gaining rating every autumn once a sub-1500 expansion club joins."""
    engine = EloEngine()
    engine.ratings = {10: 1600.0, 8: 1400.0, 54: 1380.0}
    engine._season = 20232024
    before = sum(engine.ratings.values())

    engine._roll_season(20242025)

    assert sum(engine.ratings.values()) == pytest.approx(before)


def test_first_season_teams_all_start_level() -> None:
    engine = EloEngine()
    engine.predict(make_game(season=20152016))
    assert engine.rating(10) == BASE_RATING
    assert engine.rating(8) == BASE_RATING


def test_a_club_appearing_later_starts_below_the_pack() -> None:
    engine = EloEngine()
    games = [
        make_game(game_id=1, season=20152016, date=dt.date(2016, 1, 1)),
        make_game(game_id=2, season=20172018, home_id=54, date=dt.date(2017, 10, 5)),
    ]

    predictions = list(engine.run(games))

    # Check the pregame rating: the club moves once it has played.
    assert predictions[1].home_elo_pre == EloParams().expansion_init
    assert predictions[1].away_elo_pre != EloParams().expansion_init


def test_utah_keeps_its_rating_across_the_id_change() -> None:
    """The 2025-26 rebrand issues a new team id. Without continuity the club
    would reset to an expansion rating inside the holdout season."""
    engine = EloEngine()
    games = [
        make_game(game_id=1, season=20242025, home_id=59, home_score=6, away_score=1),
        make_game(game_id=2, season=20252026, home_id=68, date=dt.date(2025, 10, 8)),
    ]
    predictions = list(engine.run(games))

    assert predictions[1].home_elo_pre > BASE_RATING
    carried = engine.rating(68)

    assert carried > BASE_RATING
    assert carried == engine.rating(59)


# -- driver -----------------------------------------------------------------


def test_run_yields_predictions_before_applying_them() -> None:
    """Walk-forward: the first prediction must not know its own result."""
    engine = EloEngine()
    games = [
        make_game(game_id=1, date=dt.date(2024, 1, 15), home_score=6, away_score=0),
        make_game(game_id=2, date=dt.date(2024, 1, 20), home_score=1, away_score=0),
    ]

    predictions = list(engine.run(games))

    assert predictions[0].home_elo_pre == BASE_RATING
    assert predictions[1].home_elo_pre > BASE_RATING
    assert predictions[0].home_won is True
