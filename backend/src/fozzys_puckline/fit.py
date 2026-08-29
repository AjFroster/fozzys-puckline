"""Parameter fitting by coordinate descent.

A full grid over five parameters is tens of thousands of passes over the game
table for no benefit: Elo parameters are close to separable, so sweeping one
axis at a time and repeating converges in about a hundred evaluations.

The point of keeping the search this small is not speed. The window is ~14,000
regular-season games of a high-variance sport, and a search with enough freedom
will always find a combination that looks excellent on the seasons it was tuned
against. Five axes and a held-out season is the guard.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from fozzys_puckline import backtest
from fozzys_puckline.params import FITTED_FIELDS, EloParams
from fozzys_puckline.schemas import Game

# Candidate values per fitted axis. Deliberately coarse — resolution finer than
# the noise floor of 14,000 games is false precision.
GRID: dict[str, tuple[float, ...]] = {
    "k": (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0),
    "hfa": (15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0),
    "ot_credit": (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.85, 1.00),
    "carryover": (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90),
    "diff_scale": (0.8, 0.9, 1.0, 1.1, 1.2, 1.4),
}

TOLERANCE = 1e-4
"""Minimum log-loss improvement required to move a parameter.

Without this the search happily walks a parameter to the edge of its grid for a
gain in the fifth decimal, which is far below the noise floor of ~14,000 games
and reliably costs real accuracy on unseen data. Measured on `mov_const`:
validation log loss was flat at 0.66336-0.66339 across 3.0 to 100, while holdout
log loss degraded monotonically from 0.68864 to 0.69027 over the same range.
"""


@dataclass(slots=True)
class FitResult:
    params: EloParams
    log_loss: float
    evaluations: int
    history: list[tuple[str, float, float]] = field(default_factory=list)
    """(field, value, log_loss) for every candidate tried."""


def fit(
    games: Sequence[Game],
    validation_seasons: Sequence[int],
    *,
    start: EloParams | None = None,
    rounds: int = 3,
    tolerance: float = TOLERANCE,
    on_progress: Callable[[str, float, float], None] | None = None,
) -> FitResult:
    """Coordinate descent on validation log loss.

    `validation_seasons` must exclude the holdout season. Nothing here ever sees
    the holdout, which is what makes the final number meaningful.
    """
    best = start or EloParams()
    history: list[tuple[str, float, float]] = []

    def score(candidate: EloParams) -> float:
        return backtest.run(
            games,
            candidate,
            eval_seasons=validation_seasons,
            keep_predictions=False,
        ).log_loss

    best_loss = score(best)
    evaluations = 1

    for _ in range(rounds):
        improved = False
        for field_name in FITTED_FIELDS:
            current = getattr(best, field_name)
            for value in GRID[field_name]:
                if value == current:
                    continue
                candidate = best.replace(**{field_name: value})
                loss = score(candidate)
                evaluations += 1
                history.append((field_name, value, loss))
                if on_progress:
                    on_progress(field_name, value, loss)
                # Strictly better by more than the noise floor, or it does not
                # count. Ties and near-ties keep the incumbent value.
                if loss < best_loss - tolerance:
                    best_loss = loss
                    best = candidate
                    improved = True
            # Re-read after the axis, so the next axis optimizes against the
            # updated point rather than the one we started the round with.
            current = getattr(best, field_name)
        if not improved:
            break

    return FitResult(params=best, log_loss=best_loss, evaluations=evaluations, history=history)
