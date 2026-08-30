"""Goal distributions, the tie correction, and the fair line."""

from __future__ import annotations

import pytest

from fozzys_puckline.goals import (
    binomial_tie,
    dispersed_series,
    final_total_distribution,
    over_under_hit_rate,
    poisson_pmf,
    poisson_series,
    tie_probability,
    total_mae,
)


def _mean(series: tuple[float, ...] | list[float]) -> float:
    return sum(k * p for k, p in enumerate(series))


def _variance(series: tuple[float, ...] | list[float]) -> float:
    mean = _mean(series)
    return sum((k - mean) ** 2 * p for k, p in enumerate(series))


# -- distributions ----------------------------------------------------------


def test_truncation_does_not_leak_probability() -> None:
    """Every distribution the model uses is renormalised, so a truncated tail
    cannot quietly remove mass from the over."""
    for lam in (2.0, 6.0, 10.0):
        for nu in (1.0, 1.162):
            assert sum(dispersed_series(lam, nu)) == pytest.approx(1.0, abs=1e-12)


def test_poisson_pmf_matches_known_value() -> None:
    assert poisson_pmf(0, 2.0) == pytest.approx(0.1353352832, abs=1e-9)


def test_dispersion_of_one_is_exactly_poisson() -> None:
    assert list(dispersed_series(6.0, 1.0)) == pytest.approx(poisson_series(6.0))


def test_dispersed_series_hits_the_requested_mean() -> None:
    """The rate parameter is not the mean once nu differs from 1."""
    for nu in (0.9, 1.0, 1.15, 1.3):
        assert _mean(dispersed_series(6.0, nu)) == pytest.approx(6.0, abs=1e-6)


def test_higher_dispersion_narrows_the_distribution() -> None:
    """NHL totals are under-dispersed, which is why nu goes above 1 and why a
    negative binomial — which can only add variance — is the wrong family."""
    poisson = _variance(dispersed_series(6.0, 1.0))
    tighter = _variance(dispersed_series(6.0, 1.2))
    assert tighter < poisson


# -- ties -------------------------------------------------------------------


def test_odd_totals_can_never_be_tied() -> None:
    assert binomial_tie(7, 0.52) == 0.0
    assert tie_probability(7, 0.52, 0.93, -0.088) == 0.0


def test_a_scoreless_game_is_always_tied() -> None:
    assert tie_probability(0, 0.52, 0.93, -0.088) == 1.0


def test_score_effects_only_ever_add_ties() -> None:
    """The correction is floored at zero: late pressure creates ties, it does
    not destroy them."""
    for total in (2, 4, 6, 8, 10):
        base = binomial_tie(total, 0.52)
        assert tie_probability(total, 0.52, 0.93, -0.088) >= base


def test_the_tie_excess_shrinks_as_the_total_grows() -> None:
    excess = [tie_probability(t, 0.52, 0.93, -0.088) - binomial_tie(t, 0.52) for t in (2, 4, 6, 8)]
    assert excess == sorted(excess, reverse=True)


def test_a_zero_correction_reduces_to_the_binomial() -> None:
    assert tie_probability(6, 0.52, 0.0, 0.0) == pytest.approx(binomial_tie(6, 0.52))


# -- the final-total transform ----------------------------------------------


def test_final_distribution_is_a_distribution() -> None:
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    assert sum(d.pmf) == pytest.approx(1.0, abs=1e-9)


def test_the_overtime_goal_raises_the_expected_total() -> None:
    """Book totals settle including overtime and the shootout, and a shootout
    winner is credited exactly one goal."""
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    assert d.expected == pytest.approx(5.8 + d.tie_probability, abs=1e-6)


def test_p_over_falls_as_the_line_rises() -> None:
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    assert d.p_over(4.5) > d.p_over(5.5) > d.p_over(6.5) > d.p_over(7.5)


def test_over_and_under_are_complementary() -> None:
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    assert d.p_over(5.5) + d.p_under(5.5) == pytest.approx(1.0)


# -- the fair line ----------------------------------------------------------


def test_the_fair_line_is_a_real_half_integer() -> None:
    """Interpolating a step function produces a number nobody can bet."""
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    line = d.fair_line()
    assert line % 1 == 0.5


def test_the_fair_line_is_the_closest_line_to_a_coin_flip() -> None:
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    line = d.fair_line()
    best = abs(d.p_over(line) - 0.5)
    for other in (line - 1.0, line + 1.0):
        if other > 0:
            assert abs(d.p_over(other) - 0.5) >= best


def test_the_published_probability_matches_the_published_line() -> None:
    d = final_total_distribution(3.0, 2.8, tie_intercept=0.8, tie_slope=-0.06)
    assert d.fair_line_p_over() == pytest.approx(d.p_over(d.fair_line()))


def test_a_higher_scoring_game_gets_a_higher_line() -> None:
    low = final_total_distribution(2.2, 2.1, tie_intercept=0.8, tie_slope=-0.06)
    high = final_total_distribution(3.8, 3.6, tie_intercept=0.8, tie_slope=-0.06)
    assert high.fair_line() > low.fair_line()


# -- scoring helpers --------------------------------------------------------


def test_hit_rate_counts_overs() -> None:
    assert over_under_hit_rate([5.5, 5.5, 5.5, 5.5], [6, 7, 5, 4]) == pytest.approx(0.5)


def test_half_integer_lines_make_pushes_impossible() -> None:
    assert over_under_hit_rate([5.5], [5]) == 0.0
    assert over_under_hit_rate([5.5], [6]) == 1.0


def test_total_mae() -> None:
    assert total_mae([6.0, 5.0], [7, 5]) == pytest.approx(0.5)
