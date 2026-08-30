"""Direct estimation of the empirical constants in the goal model.

Some quantities should not be handed to a likelihood sweep. The conditional tie
curve, the home share of goals, and the dispersion of totals are all measurable
straight off the data with far better precision than a search can find while
trading them against overall distribution shape. Letting the sweep touch them
means it will buy a slightly better fit elsewhere by moving a number we already
know, which is what happened when `tie_intercept` was fitted: it moved from a
measured 0.93 to 0.5 and made the published over/under worse.

Everything here takes an explicit season list. Nothing may be estimated on the
holdout, or the holdout stops measuring anything.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fozzys_puckline import config
from fozzys_puckline.goals import binomial_tie
from fozzys_puckline.schemas import Game
from fozzys_puckline.totals import TotalsParams

MIN_BIN = 50
"""Smallest bin worth fitting a point from."""


@dataclass(frozen=True, slots=True)
class GoalConstants:
    """Empirical constants, estimated on a stated set of seasons."""

    league_goals: float
    home_share: float
    dispersion: float
    tie_intercept: float
    tie_slope: float
    seasons: tuple[int, ...]
    games: int


def _regular_finals(games: Sequence[Game], seasons: Sequence[int]) -> list[Game]:
    wanted = set(seasons)
    return [
        g
        for g in games
        if g.season in wanted
        and g.game_type == config.REGULAR_SEASON
        and g.regulation_scores is not None
    ]


def _dispersion_for(variance_ratio: float) -> float:
    """Conway-Maxwell shape whose variance-to-mean ratio matches the data.

    Solved by bisection against the actual distribution rather than a closed
    form, since CMP has none. Ratios below 1 mean under-dispersion and give a
    shape above 1.
    """
    from fozzys_puckline.goals import dispersed_series

    def ratio_at(nu: float) -> float:
        series = dispersed_series(6.0, nu)
        mean = sum(k * p for k, p in enumerate(series))
        var = sum((k - mean) ** 2 * p for k, p in enumerate(series))
        return var / mean

    low, high = 0.5, 3.0
    for _ in range(50):
        mid = (low + high) / 2.0
        if ratio_at(mid) > variance_ratio:
            low = mid
        else:
            high = mid
    return round((low + high) / 2.0, 3)


def calibrate(games: Sequence[Game], seasons: Sequence[int]) -> GoalConstants:
    """Measure every empirical constant on the given seasons."""
    finals = _regular_finals(games, seasons)
    if not finals:
        raise ValueError("no finished regular-season games in the given seasons")

    home_goals = 0
    away_goals = 0
    totals: list[int] = []
    by_total: dict[int, list[int]] = {}

    for game in finals:
        regulation = game.regulation_scores
        assert regulation is not None
        home, away = regulation
        home_goals += home
        away_goals += away
        total = home + away
        totals.append(game.total_goals or 0)
        by_total.setdefault(total, []).append(int(home == away))

    n = len(finals)
    league_goals = (home_goals + away_goals) / (2 * n)
    home_share = home_goals / (home_goals + away_goals)

    mean = sum(totals) / n
    variance = sum((t - mean) ** 2 for t in totals) / n
    dispersion = _dispersion_for(variance / mean)

    intercept, slope = _fit_tie_curve(by_total, home_share)

    return GoalConstants(
        league_goals=round(league_goals, 4),
        home_share=round(home_share, 4),
        dispersion=dispersion,
        tie_intercept=round(intercept, 4),
        tie_slope=round(slope, 4),
        seasons=tuple(sorted(set(seasons))),
        games=n,
    )


def _fit_tie_curve(by_total: dict[int, list[int]], home_share: float) -> tuple[float, float]:
    """Weighted least squares of the log-odds tie excess against the total.

    The excess over the binomial baseline is close to linear in the total once
    expressed in log odds, so two parameters describe it. Bins are weighted by
    their game count, since a bin of 2,500 games says far more than one of 60.
    """
    xs: list[float] = []
    ys: list[float] = []
    weights: list[float] = []

    for total, flags in sorted(by_total.items()):
        if total % 2 or total == 0 or len(flags) < MIN_BIN:
            continue
        observed = sum(flags) / len(flags)
        base = binomial_tie(total, home_share)
        if not 0.0 < observed < 1.0 or not 0.0 < base < 1.0:
            continue
        excess = math.log(observed / (1 - observed)) - math.log(base / (1 - base))
        xs.append(float(total))
        ys.append(excess)
        weights.append(float(len(flags)))

    if len(xs) < 2:
        return 0.0, 0.0

    total_weight = sum(weights)
    mean_x = sum(w * x for w, x in zip(weights, xs, strict=True)) / total_weight
    mean_y = sum(w * y for w, y in zip(weights, ys, strict=True)) / total_weight
    covariance = sum(
        w * (x - mean_x) * (y - mean_y) for w, x, y in zip(weights, xs, ys, strict=True)
    )
    variance = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, xs, strict=True))
    slope = covariance / variance if variance else 0.0
    return mean_y - slope * mean_x, slope


def observed_tie_rate(games: Sequence[Game], seasons: Sequence[int]) -> float:
    """Share of regular-season finals that went past regulation."""
    finals = _regular_finals(games, seasons)
    return sum(1 for g in finals if g.went_past_regulation) / len(finals)


def match_tie_marginal(
    games: Sequence[Game],
    seasons: Sequence[int],
    params: TotalsParams,
    *,
    iterations: int = 40,
) -> TotalsParams:
    """Shift the tie intercept so the model's *marginal* tie rate is right.

    The weighted least squares fit gets the shape of the conditional tie curve,
    but it minimises squared error in log odds, which does not preserve the
    aggregate. Left alone it under-states the marginal by about two points, and
    since every tie adds exactly one goal, that lands directly on every total
    the model publishes as a level bias.

    So: the slope carries the shape, and the intercept is solved to make the
    marginal come out right. Only the seasons passed in are ever consulted.
    """
    from fozzys_puckline.totals import TotalsEngine

    wanted = set(seasons)
    target = observed_tie_rate(games, seasons)

    def modelled(intercept: float) -> float:
        candidate = params.replace(tie_intercept=intercept)
        predictions = [
            p
            for p in TotalsEngine(params=candidate).run(games)
            if p.scored and p.game_type == config.REGULAR_SEASON and p.season in wanted
        ]
        return sum(p.tie_probability for p in predictions) / len(predictions)

    low, high = -2.0, 6.0
    for _ in range(iterations):
        mid = (low + high) / 2.0
        if modelled(mid) < target:
            low = mid
        else:
            high = mid
        if high - low < 1e-4:
            break
    return params.replace(tie_intercept=round((low + high) / 2.0, 4))
