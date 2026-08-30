"""The goal-rate engine."""

from __future__ import annotations

import datetime as dt

import pytest

from fozzys_puckline.schemas import Game
from fozzys_puckline.totals import TotalsEngine, TotalsParams, mean_log_likelihood


def make_game(
    game_id: int = 1,
    *,
    season: int = 20232024,
    date: dt.date | None = None,
    home_id: int = 10,
    away_id: int = 8,
    home_score: int = 3,
    away_score: int = 2,
    last_period: str = "REG",
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
        state="FINAL",
    )


# -- regulation reconstruction ---------------------------------------------


def test_regulation_equals_final_in_a_regulation_game() -> None:
    assert make_game(home_score=4, away_score=1).regulation_scores == (4, 1)


def test_an_overtime_winner_gives_back_its_goal() -> None:
    assert make_game(home_score=3, away_score=2, last_period="OT").regulation_scores == (2, 2)


def test_a_shootout_winner_gives_back_exactly_one_goal() -> None:
    """The shootout is credited as a single goal regardless of the round score."""
    game = make_game(home_score=2, away_score=3, last_period="SO")
    assert game.regulation_scores == (2, 2)


def test_reconstructed_regulation_is_always_tied_past_regulation() -> None:
    for last in ("OT", "SO"):
        for home, away in ((5, 4), (1, 2), (3, 2)):
            game = make_game(home_score=home, away_score=away, last_period=last)
            regulation = game.regulation_scores
            assert regulation is not None
            assert regulation[0] == regulation[1]


def test_an_unfinished_game_has_no_regulation_score() -> None:
    game = Game(
        game_id=1,
        season=20232024,
        game_type=2,
        date_et=dt.date(2024, 1, 15),
        home_id=10,
        away_id=8,
        home_abbrev="TOR",
        away_abbrev="MTL",
        state="FUT",
    )
    assert game.regulation_scores is None


# -- the engine -------------------------------------------------------------


def test_a_team_with_no_history_predicts_league_average() -> None:
    engine = TotalsEngine()
    prediction = engine.predict(make_game())
    expected = 2.0 * engine.league_goals()
    assert prediction.exp_goals_home + prediction.exp_goals_away == pytest.approx(expected)


def test_the_home_team_is_expected_to_score_more() -> None:
    prediction = TotalsEngine().predict(make_game())
    assert prediction.exp_goals_home > prediction.exp_goals_away


def test_a_high_scoring_team_raises_its_own_expected_goals() -> None:
    engine = TotalsEngine()
    before = engine.predict(make_game()).exp_goals_home
    for i in range(40):
        engine.observe(make_game(game_id=i + 2, home_score=7, away_score=1))
    assert engine.predict(make_game()).exp_goals_home > before


def test_rates_use_regulation_goals_not_final_ones() -> None:
    """Learning from final scores would fold the overtime goal into every
    team's attack rate and inflate every total the model publishes."""
    from_regulation = TotalsEngine()
    from_final = TotalsEngine()
    for i in range(40):
        from_regulation.observe(make_game(game_id=i, home_score=4, away_score=3, last_period="OT"))
        from_final.observe(make_game(game_id=i, home_score=3, away_score=3))

    a = from_regulation.predict(make_game()).exp_total
    b = from_final.predict(make_game()).exp_total
    assert a == pytest.approx(b)


def test_a_team_only_ages_on_its_own_games() -> None:
    """Ageing every team on every league game applies the half-life about
    sixteen times too fast and collapses every multiplier onto the prior."""
    engine = TotalsEngine(params=TotalsParams(half_life=20.0))
    for i in range(40):
        engine.observe(make_game(game_id=i, home_id=10, away_id=8, home_score=6, away_score=0))
    # Two teams playing 40 games between them should carry real weight, not the
    # fraction they would hold if every game aged them.
    assert engine.rates[10].weight > 15.0


def test_run_predicts_before_learning_from_the_result() -> None:
    engine = TotalsEngine()
    games = [make_game(game_id=i, home_score=8, away_score=0) for i in range(3)]
    predictions = list(engine.run(games))
    assert predictions[1].exp_goals_home > predictions[0].exp_goals_home


def test_predictions_carry_the_published_lines() -> None:
    prediction = TotalsEngine().predict(make_game())
    assert [line for line, _ in prediction.lines] == [5.5, 6.5]
    assert prediction.p_over(5.5) is not None
    assert prediction.p_over(9.5) is None


def test_the_fair_line_probability_is_near_a_coin_flip() -> None:
    prediction = TotalsEngine().predict(make_game())
    assert abs(prediction.fair_line_p_over - 0.5) < 0.08


def test_log_likelihood_ignores_unplayed_games() -> None:
    engine = TotalsEngine()
    played = engine.predict(make_game())
    assert mean_log_likelihood([played]) < 0.0
    assert mean_log_likelihood([]) != mean_log_likelihood([])  # nan
