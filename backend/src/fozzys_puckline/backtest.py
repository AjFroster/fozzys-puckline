"""Walk-forward backtesting.

Every game is predicted using only ratings that existed before it. Ratings warm
up across the whole history; scoring happens only inside the evaluation window,
so early seasons inform the model without being graded by it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from fozzys_puckline import config, store
from fozzys_puckline.elo import EloEngine, GamePrediction
from fozzys_puckline.metrics import Evaluation, evaluate
from fozzys_puckline.params import EloParams
from fozzys_puckline.schemas import Game

DEFAULT_HOLDOUT = 20252026
"""The most recent completed season, held out until parameters are frozen.

Worth knowing what this particular season is: 2025-26 carried a 20-day Olympic
break (2026-02-05 to 2026-02-25), the highest past-regulation rate in the window
at 24.96%, and the lowest home win rate at 52.21%. It is the hardest season
available, which makes it a conservative holdout rather than a flattering one.
"""

WARMUP_SEASONS = 3
"""Seasons spent letting ratings settle before anything is scored."""


def evaluation_windows(
    games: Sequence[Game],
    holdout: int = DEFAULT_HOLDOUT,
    warmup: int = WARMUP_SEASONS,
) -> tuple[list[int], list[int]]:
    """Split the seasons into (validation, holdout).

    Fitting never sees the holdout, and neither window includes the warmup
    seasons or anything after the holdout.
    """
    seasons = sorted({g.season for g in games if g.season <= holdout})
    validation = [s for s in seasons[warmup:] if s != holdout]
    return validation, [holdout]


def load_ordered_games(path: object = None) -> list[Game]:
    """The full game table in strict chronological order."""
    frame = store.load_games(path)  # type: ignore[arg-type]
    if frame.is_empty():
        return []
    return store.frame_to_games(frame.sort(["date_et", "game_id"]))


def is_scorable(
    prediction: GamePrediction,
    seasons: Sequence[int] | None,
    exclude_no_fans: bool,
) -> bool:
    """Should this prediction count toward the metrics?

    Playoffs are excluded from scoring: short series against a narrow set of
    opponents are not a representative sample, even though the results still
    update ratings.
    """
    if not prediction.scored:
        return False
    if prediction.game_type != config.REGULAR_SEASON:
        return False
    if seasons is not None and prediction.season not in seasons:
        return False
    return not (exclude_no_fans and (prediction.no_fans or prediction.neutral_site))


@dataclass(slots=True)
class BacktestResult:
    params: EloParams
    evaluation: Evaluation
    predictions: list[GamePrediction] = field(default_factory=list)
    ratings: dict[int, float] = field(default_factory=dict)

    @property
    def log_loss(self) -> float:
        return self.evaluation.log_loss


def run(
    games: Iterable[Game],
    params: EloParams,
    *,
    eval_seasons: Sequence[int] | None = None,
    exclude_no_fans: bool = True,
    keep_predictions: bool = True,
) -> BacktestResult:
    """Rate every game in order and score the ones inside the window.

    `keep_predictions=False` during a parameter sweep — holding a hundred
    thousand prediction records per candidate is pure overhead.
    """
    engine = EloEngine(params=params)
    probs: list[float] = []
    outcomes: list[bool] = []
    kept: list[GamePrediction] = []

    for prediction in engine.run(games):
        if not is_scorable(prediction, eval_seasons, exclude_no_fans):
            continue
        probs.append(prediction.home_win_prob)
        assert prediction.home_won is not None  # guaranteed by is_scorable
        outcomes.append(prediction.home_won)
        if keep_predictions:
            kept.append(prediction)

    return BacktestResult(
        params=params,
        evaluation=evaluate(probs, outcomes),
        predictions=kept,
        ratings=dict(engine.ratings),
    )
