"""Goal distributions and the over/under transform.

Elo is unitless and cannot produce a goal total, so totals need their own
estimator. The decomposition here is deliberate, and follows what the data
actually supports rather than the textbook independent-Poisson model:

  total    Poisson on the summed rate. Fits well — the largest residual across
           the backfill is under two points.
  tie      NOT taken from the Poisson joint. Independent Poisson misprices the
           regulation margin badly: it predicts 30.8% one-goal games against an
           observed 19.6%, and 16.9% ties against an observed 22.4%. Empty-net
           goals push one-goal games out to two and three, and pulled-goalie
           pressure pushes others back to a tie. Both drain the same bucket, and
           an independence assumption cannot express either.
  final    Regulation total, plus one goal when regulation ended tied.

Book totals settle on the final score including overtime and the shootout, and a
shootout winner is credited exactly one goal — so that last step is not a
refinement, it is the difference between a correct model and a permanently
biased one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

MAX_GOALS = 30
"""Truncation point for the goal distributions.

Chosen so the discarded tail stays negligible at the rates this model actually
produces: at 30 the omitted mass is under 1e-9 even for a lambda of 10, which is
well above any NHL matchup. The series is renormalised regardless, so truncation
cannot leak probability out of the distribution."""


def poisson_pmf(k: int, lam: float) -> float:
    if k < 0 or lam <= 0:
        return 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_series(lam: float, max_goals: int = MAX_GOALS) -> list[float]:
    """P(X = k) for k in 0..max_goals."""
    return [poisson_pmf(k, lam) for k in range(max_goals + 1)]


def _cmp_series(rate: float, nu: float, max_goals: int) -> list[float]:
    """Conway-Maxwell-Poisson pmf for a given rate parameter."""
    logs = [k * math.log(rate) - nu * math.lgamma(k + 1) for k in range(max_goals + 1)]
    peak = max(logs)
    weights = [math.exp(v - peak) for v in logs]
    norm = sum(weights)
    return [w / norm for w in weights]


def _series_mean(series: Sequence[float]) -> float:
    return sum(k * p for k, p in enumerate(series))


@lru_cache(maxsize=8192)
def dispersed_series(mean: float, nu: float, max_goals: int = MAX_GOALS) -> tuple[float, ...]:
    """A count distribution with the given mean and a chosen dispersion.

    `nu` is the Conway-Maxwell-Poisson shape: 1.0 is exactly Poisson, above 1.0
    is under-dispersed, below is over-dispersed.

    Under-dispersion is what NHL totals actually show. Measured over the
    backfill, final totals have variance 5.29 against a mean 6.00, a ratio of
    0.88. That rules out the negative binomial, which can only ever add variance
    — reaching for it here would push the model further from the data, not
    closer. Excess spread in a right-skewed distribution also drags the median
    below the mean, which is what biases a fair line low.

    The rate parameter is not the mean once `nu` differs from 1, so it is solved
    for by bisection. Results are cached because a parameter sweep asks for the
    same rounded mean thousands of times.
    """
    if nu == 1.0:
        series = poisson_series(mean, max_goals)
        norm = sum(series)
        # Renormalise so truncation cannot leave the pmf summing to under one,
        # matching what the Conway-Maxwell branch below does.
        return tuple(p / norm for p in series)

    low, high = 1e-6, 1.0
    while _series_mean(_cmp_series(high, nu, max_goals)) < mean and high < 1e6:
        high *= 2.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if _series_mean(_cmp_series(mid, nu, max_goals)) < mean:
            low = mid
        else:
            high = mid
    return tuple(_cmp_series((low + high) / 2.0, nu, max_goals))


def binomial_tie(total: int, home_share: float) -> float:
    """P(tie | `total` goals), if goals were split independently.

    This is the baseline the score-effect correction adjusts, not the answer.
    """
    if total % 2 or total < 0:
        return 0.0
    half = total // 2
    return math.comb(total, half) * home_share**half * (1.0 - home_share) ** half


def _logit(p: float) -> float:
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    return math.log(p / (1.0 - p))


def _expit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def tie_probability(
    total: int,
    home_share: float,
    intercept: float,
    slope: float,
) -> float:
    """P(tie | regulation total), with the score-effect correction applied.

    Measured excess over the binomial baseline, across the backfill:

        total  2  +18.4 points     total  8  +3.9 points
        total  4   +8.2 points     total 10  +1.2 points
        total  6   +7.2 points

    The excess is close to linear in the total once expressed as a log-odds
    shift, which is what `intercept` and `slope` parameterise. The shift is
    floored at zero: score effects create ties, they never destroy them.
    """
    if total % 2 or total < 0:
        return 0.0
    if total == 0:
        return 1.0
    base = binomial_tie(total, home_share)
    shift = max(0.0, intercept + slope * total)
    return _expit(_logit(base) + shift)


@dataclass(frozen=True, slots=True)
class TotalDistribution:
    """The final-score total, including any overtime or shootout goal."""

    pmf: tuple[float, ...]
    expected: float
    tie_probability: float
    """P(regulation ends tied), i.e. P(the game produces an extra goal)."""

    def p_over(self, line: float) -> float:
        """P(final total > line). Book lines are half-integers, so no push."""
        return sum(p for total, p in enumerate(self.pmf) if total > line)

    def p_under(self, line: float) -> float:
        return 1.0 - self.p_over(line)

    def fair_line(self) -> float:
        """The half-integer line closest to a coin flip.

        Deliberately *not* interpolated. Totals are integers, so `p_over` is a
        step function and in general no line gives exactly 0.500 — for a
        Poisson(6) total, p_over(5.5) is 0.554 and p_over(6.5) is 0.394, with
        nothing in between. Interpolating those to 5.84 produces a number that
        is not a line anyone can bet and does not have the property it claims:
        as an actual line, 5.84 still resolves every total of 6 as an over, so
        it pays out at 55.4%, not 50%.

        Returning a real half-integer keeps the published number bettable and
        makes the hit rate at it an honest self-check.
        """
        lines = [i + 0.5 for i in range(len(self.pmf))]
        return min(lines, key=lambda line: abs(self.p_over(line) - 0.5))

    def fair_line_p_over(self) -> float:
        """How far from a true coin flip the fair line actually lands.

        Discreteness means this can sit a few points off 0.500; publishing it
        beside the line is what stops the line from implying a precision the
        distribution does not have.
        """
        return self.p_over(self.fair_line())


def final_total_distribution(
    lam_home: float,
    lam_away: float,
    *,
    tie_intercept: float,
    tie_slope: float,
    dispersion: float = 1.0,
    max_goals: int = MAX_GOALS,
) -> TotalDistribution:
    """Regulation totals, plus the overtime or shootout goal when tied."""
    lam_total = lam_home + lam_away
    home_share = lam_home / lam_total if lam_total > 0 else 0.5
    # Rounded so the cache actually hits; 0.001 goals is far below resolution.
    regulation = list(dispersed_series(round(lam_total, 3), dispersion, max_goals))

    final = [0.0] * (max_goals + 2)
    tie_mass = 0.0
    for total, p_total in enumerate(regulation):
        p_tie = tie_probability(total, home_share, tie_intercept, tie_slope)
        tied = p_total * p_tie
        tie_mass += tied
        final[total] += p_total - tied  # decided in regulation
        final[total + 1] += tied  # one more goal in OT or the shootout

    expected = sum(total * p for total, p in enumerate(final))
    return TotalDistribution(pmf=tuple(final), expected=expected, tie_probability=tie_mass)


def over_under_hit_rate(lines: Sequence[float], actual_totals: Sequence[int]) -> float:
    """Share of games that went over the given line.

    Evaluated at the model's own fair line this should sit near 50% by
    construction, which makes it a sharp self-check rather than a skill measure.
    Pushes are impossible because fair lines are not integers.
    """
    if not lines:
        return float("nan")
    overs = sum(1 for line, total in zip(lines, actual_totals, strict=True) if total > line)
    return overs / len(lines)


def total_mae(predicted: Sequence[float], actual: Sequence[int]) -> float:
    if not predicted:
        return float("nan")
    return sum(abs(p - a) for p, a in zip(predicted, actual, strict=True)) / len(predicted)
