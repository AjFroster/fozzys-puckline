"""The JSON contract between this backend and the site.

These models generate everything under `web/public/data/v1/`, and
`web/src/types/contract.ts` mirrors them by hand. The path is versioned, so a
breaking change ships as `/v2/` and gains a sibling rather than being edited in
place. Contract tests check the shape on every commit.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"

GameState = Literal["FUT", "PRE", "LIVE", "OFF", "FINAL"]
LastPeriod = Literal["REG", "OT", "SO"]


class Document(BaseModel):
    """Fields every published file carries.

    The generation stamp and model version are on every document on purpose:
    the site shows them, so stale data is visible as stale rather than silently
    presented as current.
    """

    schema_version: str = Field(default=SCHEMA_VERSION, serialization_alias="schema")
    generated_at: dt.datetime
    model_version: str


class TeamSide(BaseModel):
    abbrev: str
    elo: float
    rest_days: int | None = None
    b2b: bool = False


class TotalLine(BaseModel):
    line: float
    p_over: float


class Prediction(BaseModel):
    home_win_prob: float
    away_win_prob: float
    home_ml_fair: int
    away_ml_fair: int
    home_decimal_fair: float
    away_decimal_fair: float
    exp_goals_home: float
    exp_goals_away: float
    exp_total: float
    fair_total_line: float
    fair_line_p_over: float
    totals: list[TotalLine]


class GameResult(BaseModel):
    home_score: int
    away_score: int
    last_period: LastPeriod
    total_goals: int
    home_won: bool


class SlateGame(BaseModel):
    game_id: int
    start_utc: dt.datetime | None = None
    state: GameState
    venue: str | None = None
    home: TeamSide
    away: TeamSide
    prediction: Prediction
    result: GameResult | None = None
    """Null until the grading job fills it in the next morning."""


class Slate(Document):
    date: dt.date
    games: list[SlateGame]


class TeamRating(BaseModel):
    team_id: int
    abbrev: str
    name: str
    elo: float
    """Current rating, including any between-season regression already applied.
    This is the number the upcoming slate is predicted from."""
    rank: int
    percentile: float
    elo_7d_change: float
    """Movement over the last seven days the league actually played.

    Measured between two in-season snapshots rather than against `elo`, which
    may sit on the far side of a season rollover.
    """
    win_prob_vs_average: float
    """Win probability against a league-average opponent on neutral ice."""


class Ratings(Document):
    season: int
    teams: list[TeamRating]


class RatingPoint(BaseModel):
    date: dt.date
    elo: dict[str, float]
    """Team abbreviation to rating, for that day."""


class RatingHistory(Document):
    season: int
    points: list[RatingPoint]


class Team(BaseModel):
    team_id: int
    abbrev: str
    name: str
    logo: str


class Teams(Document):
    teams: list[Team]


class CalibrationBin(BaseModel):
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed: float
    z: float


class WindowMetrics(BaseModel):
    label: str
    seasons: list[int]
    games: int
    log_loss: float
    baseline_log_loss: float
    log_loss_skill: float
    brier: float
    brier_skill: float
    accuracy: float
    baseline_accuracy: float
    worst_calibration_z: float
    calibration_threshold: float
    well_calibrated: bool
    calibration: list[CalibrationBin]


class TotalsMetrics(BaseModel):
    label: str
    games: int
    over_under_hit_rate: float
    model_claimed_rate: float
    total_mae: float
    mean_log_likelihood: float
    modelled_tie_rate: float
    actual_tie_rate: float


class SeasonMetrics(BaseModel):
    season: int
    games: int
    log_loss: float
    baseline_log_loss: float
    accuracy: float


class RecentForm(BaseModel):
    """How the model has done over the most recently graded games.

    The season windows are the honest evaluation, but they are historical. This
    is the number someone actually wants when they open the page mid-season:
    how is it doing *now*, wins and losses both.
    """

    games: int
    since: dt.date
    through: dt.date
    log_loss: float
    baseline_log_loss: float
    accuracy: float
    correct: int
    over_under_hit_rate: float
    total_mae: float


class Metrics(Document):
    holdout_season: int
    recent: RecentForm | None = None
    windows: list[WindowMetrics]
    totals: list[TotalsMetrics]
    by_season: list[SeasonMetrics]


class TrackPoint(BaseModel):
    """One game day in the season-to-date record."""

    date: dt.date
    games_today: int
    correct_today: int

    # Cumulative from the start of the season.
    games: int
    correct: int
    accuracy: float
    log_loss: float
    baseline_log_loss: float
    brier: float
    over_under_hit_rate: float

    # Trailing window, so a cold streak is visible instead of being averaged
    # away by everything that came before it.
    rolling_accuracy: float | None = None
    rolling_log_loss: float | None = None


class NotableGame(BaseModel):
    """A game the model called confidently and got wrong."""

    date: dt.date
    game_id: int
    winner: str
    loser: str
    probability_given_to_winner: float
    score: str


class SeasonTrack(Document):
    """How the predictions have actually done, day by day, this season.

    Separate from `metrics.json` on purpose. That file is the historical
    evaluation — fixed windows, fitted parameters, a holdout. This one is the
    live scoreboard for the season in progress, and it answers a different
    question: not "is the model sound" but "how is it doing right now".
    """

    season: int
    complete: bool
    """False while the season is still being played."""
    through: dt.date | None = None
    rolling_window: int
    summary: TrackPoint | None = None
    points: list[TrackPoint]
    calibration: list[CalibrationBin]
    worst_calibration_z: float
    calibration_threshold: float
    well_calibrated: bool
    biggest_misses: list[NotableGame]


class IndexEntry(BaseModel):
    date: dt.date
    games: int


class Index(Document):
    latest_date: dt.date | None = None
    """The date `latest.json` points at — today if there are games, else the
    next scheduled game day."""
    dates: list[IndexEntry]
