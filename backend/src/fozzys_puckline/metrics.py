"""Evaluation metrics.

The NHL is the highest-variance of the four major leagues, so accuracy is a poor
headline number: a model can look impressive by picking home teams and learn
nothing. Log loss against a baseline is the honest measure, and calibration is
what says whether a published "62%" means anything.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

EPSILON = 1e-15


def _clip(p: float) -> float:
    return min(max(p, EPSILON), 1.0 - EPSILON)


def log_loss(probs: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean negative log likelihood. Lower is better."""
    if not probs:
        return float("nan")
    total = 0.0
    for p, actual in zip(probs, outcomes, strict=True):
        q = _clip(p)
        total += -math.log(q) if actual else -math.log(1.0 - q)
    return total / len(probs)


def brier_score(probs: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean squared error of the probability. Lower is better."""
    if not probs:
        return float("nan")
    return sum((p - float(a)) ** 2 for p, a in zip(probs, outcomes, strict=True)) / len(probs)


def accuracy(probs: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Straight-up hit rate at a 0.5 threshold."""
    if not probs:
        return float("nan")
    hits = sum(1 for p, a in zip(probs, outcomes, strict=True) if (p >= 0.5) == a)
    return hits / len(probs)


def skill_score(model: float, baseline: float) -> float:
    """Fractional improvement over a baseline. Positive means better."""
    if baseline == 0:
        return float("nan")
    return 1.0 - (model / baseline)


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed: float

    @property
    def gap(self) -> float:
        """Predicted minus observed, in probability points."""
        return self.mean_predicted - self.observed

    @property
    def standard_error(self) -> float:
        """Sampling error on the observed rate in this bin."""
        if self.count == 0:
            return float("inf")
        return math.sqrt(self.observed * (1.0 - self.observed) / self.count)

    @property
    def z(self) -> float:
        """Gap in standard errors. This is the number worth gating on.

        A fixed points-based threshold is not a meaningful test here: a bin
        holding 30 games carries about 18 points of 2-sigma sampling noise, so a
        raw 11-point gap there is unremarkable, while a 4-point gap in a bin of
        1,800 is a real miscalibration. Comparing everything to one points
        threshold flags the first and misses the second.
        """
        se = self.standard_error
        return abs(self.gap) / se if se else 0.0


def calibration(
    probs: Sequence[float], outcomes: Sequence[bool], bins: int = 10
) -> list[CalibrationBin]:
    """Reliability table: of games called 60%, do ~60% actually win?"""
    buckets: list[tuple[list[float], list[bool]]] = [([], []) for _ in range(bins)]
    for p, actual in zip(probs, outcomes, strict=True):
        index = min(int(p * bins), bins - 1)
        buckets[index][0].append(p)
        buckets[index][1].append(actual)

    table: list[CalibrationBin] = []
    for i, (ps, outs) in enumerate(buckets):
        if not ps:
            continue
        table.append(
            CalibrationBin(
                lower=i / bins,
                upper=(i + 1) / bins,
                count=len(ps),
                mean_predicted=sum(ps) / len(ps),
                observed=sum(outs) / len(outs),
            )
        )
    return table


def max_calibration_gap(table: Sequence[CalibrationBin], min_count: int = 30) -> float:
    """Worst bin miss in probability points, ignoring bins too thin to read."""
    gaps = [abs(b.gap) for b in table if b.count >= min_count]
    return max(gaps) if gaps else 0.0


def worst_calibration_z(table: Sequence[CalibrationBin], min_count: int = 30) -> float:
    """Worst bin miss in standard errors."""
    zs = [b.z for b in table if b.count >= min_count]
    return max(zs) if zs else 0.0


FAMILYWISE_ALPHA = 0.05


def calibration_threshold(tested_bins: int, alpha: float = FAMILYWISE_ALPHA) -> float:
    """Bonferroni-corrected two-sided z threshold for `tested_bins` bins.

    Every populated bin is a separate test, so comparing each one against a flat
    2-sigma line asks the model to pass five-ish coin flips at once: a perfectly
    calibrated model fails that about 21% of the time on five bins. Correcting
    for the number of bins is what makes "well calibrated" mean something.
    """
    if tested_bins <= 0:
        return float("inf")
    return float(statistics.NormalDist().inv_cdf(1.0 - alpha / (2.0 * tested_bins)))


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Everything the model page needs to publish about one evaluation window."""

    games: int
    log_loss: float
    brier: float
    accuracy: float
    baseline_rate: float
    baseline_log_loss: float
    baseline_brier: float
    baseline_accuracy: float
    calibration: tuple[CalibrationBin, ...]

    @property
    def log_loss_skill(self) -> float:
        return skill_score(self.log_loss, self.baseline_log_loss)

    @property
    def brier_skill(self) -> float:
        return skill_score(self.brier, self.baseline_brier)

    @property
    def max_gap(self) -> float:
        return max_calibration_gap(self.calibration)

    @property
    def worst_z(self) -> float:
        return worst_calibration_z(self.calibration)

    @property
    def tested_bins(self) -> int:
        """Bins holding enough games to say anything about."""
        return sum(1 for b in self.calibration if b.count >= 30)

    @property
    def calibration_threshold(self) -> float:
        return calibration_threshold(self.tested_bins)

    @property
    def well_calibrated(self) -> bool:
        """No bin misses by more than the corrected threshold."""
        return self.worst_z <= self.calibration_threshold

    @property
    def beats_baseline(self) -> bool:
        return self.log_loss < self.baseline_log_loss


def evaluate(probs: Sequence[float], outcomes: Sequence[bool], bins: int = 10) -> Evaluation:
    """Score a set of predictions against the always-home baseline.

    The baseline predicts the base rate of home wins in the same window for
    every game — the least informative model that still knows home ice exists.
    Beating it is the minimum bar for the engine to be worth anything.
    """
    n = len(probs)
    rate = (sum(1 for a in outcomes if a) / n) if n else float("nan")
    flat = [rate] * n

    return Evaluation(
        games=n,
        log_loss=log_loss(probs, outcomes),
        brier=brier_score(probs, outcomes),
        accuracy=accuracy(probs, outcomes),
        baseline_rate=rate,
        baseline_log_loss=log_loss(flat, outcomes),
        baseline_brier=brier_score(flat, outcomes),
        baseline_accuracy=accuracy(flat, outcomes),
        calibration=tuple(calibration(probs, outcomes, bins)),
    )
