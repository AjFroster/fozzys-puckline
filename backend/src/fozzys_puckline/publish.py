"""Build the JSON the site reads.

One walk-forward pass drives both models, so every published prediction is the
one the model would have made with only the information available before that
game. Nothing here re-reads a result before predicting it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fozzys_puckline import config, contracts, odds
from fozzys_puckline import metrics as metrics_mod
from fozzys_puckline.backtest import DEFAULT_HOLDOUT, evaluation_windows, is_scorable
from fozzys_puckline.calibrate import observed_tie_rate
from fozzys_puckline.elo import EloEngine, GamePrediction, expected_score
from fozzys_puckline.goals import over_under_hit_rate, total_mae
from fozzys_puckline.identity import rating_key
from fozzys_puckline.params import BASE_RATING, ModelParams
from fozzys_puckline.schemas import Game
from fozzys_puckline.store import read_snapshot
from fozzys_puckline.totals import TotalsEngine, TotalsPrediction, mean_log_likelihood

ELO_VERSION = "elo-1.0"
TOTALS_VERSION = "cmp-1.0"

LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg"

RECENT_GAME_DAYS = 30
"""How many past game days to publish slates for."""

UPCOMING_GAME_DAYS = 7
"""How many future game days to publish slates for.

Counted in game days rather than calendar days so the site still has something
to show during the offseason, when the next puck drop is months away.
"""


def model_version(params: ModelParams) -> str:
    """Version string that changes whenever the parameters do.

    Published on every document, so a prediction can always be traced back to
    the exact model that produced it.
    """
    payload = json.dumps(
        {"elo": asdict(params.elo), "totals": asdict(params.totals)}, sort_keys=True
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:7]
    return f"{ELO_VERSION}+{TOTALS_VERSION}/{digest}"


@dataclass(slots=True)
class ModelRun:
    """Everything one walk-forward pass produces."""

    elo: dict[int, GamePrediction] = field(default_factory=dict)
    totals: dict[int, TotalsPrediction] = field(default_factory=dict)
    ratings: dict[int, float] = field(default_factory=dict)
    history: list[tuple[dt.date, dict[int, float]]] = field(default_factory=list)
    labels: dict[int, str] = field(default_factory=dict)


def run_models(games: Sequence[Game], params: ModelParams) -> ModelRun:
    """Drive both engines over the full history in one ordered pass."""
    elo_engine = EloEngine(params=params.elo)
    totals_engine = TotalsEngine(params=params.totals)
    run = ModelRun()

    current_date: dt.date | None = None
    played_today = False
    for game in games:
        if current_date is not None and game.date_et != current_date:
            # Only snapshot days that actually moved ratings. Scheduled-but-
            # unplayed days would otherwise pad the history with flat repeats,
            # which makes every team's 7-day change read as zero.
            if played_today:
                run.history.append((current_date, dict(elo_engine.ratings)))
            played_today = False
        current_date = game.date_et
        played_today = played_today or game.is_final

        elo_engine._roll_season(game.season)
        totals_engine._roll_season(game.season)

        elo_prediction = elo_engine.predict(game)
        run.elo[game.game_id] = elo_prediction
        run.totals[game.game_id] = totals_engine.predict(game)

        elo_engine.observe(game, elo_prediction)
        totals_engine.observe(game)

        run.labels[rating_key(game.home_id)] = game.home_abbrev
        run.labels[rating_key(game.away_id)] = game.away_abbrev

    if current_date is not None and played_today:
        run.history.append((current_date, dict(elo_engine.ratings)))
    run.ratings = dict(elo_engine.ratings)
    return run


# --------------------------------------------------------------------------
# slates


def slate_dates(
    games: Sequence[Game],
    today: dt.date,
    recent: int = RECENT_GAME_DAYS,
    upcoming: int = UPCOMING_GAME_DAYS,
) -> list[dt.date]:
    """Game days worth publishing: the recent past plus the near future."""
    all_dates = sorted({g.date_et for g in games})
    past = [d for d in all_dates if d <= today][-recent:]
    future = [d for d in all_dates if d > today][:upcoming]
    return past + future


def latest_date(games: Sequence[Game], today: dt.date) -> dt.date | None:
    """Today if the league is playing, otherwise the next scheduled game day.

    Without the fallback the homepage is blank for the whole offseason.
    """
    all_dates = sorted({g.date_et for g in games})
    if today in all_dates:
        return today
    future = [d for d in all_dates if d > today]
    if future:
        return future[0]
    return all_dates[-1] if all_dates else None


def build_slate_game(
    game: Game, elo: GamePrediction, totals: TotalsPrediction
) -> contracts.SlateGame:
    home_prob = elo.home_win_prob
    away_prob = 1.0 - home_prob

    result = None
    if game.is_final and game.home_score is not None and game.away_score is not None:
        result = contracts.GameResult(
            home_score=game.home_score,
            away_score=game.away_score,
            last_period=game.last_period or "REG",
            total_goals=game.total_goals or 0,
            home_won=game.home_score > game.away_score,
        )

    return contracts.SlateGame(
        game_id=game.game_id,
        start_utc=game.start_utc,
        state=game.state,
        venue=game.venue,
        home=contracts.TeamSide(
            abbrev=game.home_abbrev,
            elo=round(elo.home_elo_pre, 1),
            rest_days=elo.home_rest_days,
            b2b=elo.home_b2b,
        ),
        away=contracts.TeamSide(
            abbrev=game.away_abbrev,
            elo=round(elo.away_elo_pre, 1),
            rest_days=elo.away_rest_days,
            b2b=elo.away_b2b,
        ),
        prediction=contracts.Prediction(
            home_win_prob=round(home_prob, 4),
            away_win_prob=round(away_prob, 4),
            home_ml_fair=odds.american_odds(home_prob),
            away_ml_fair=odds.american_odds(away_prob),
            home_decimal_fair=odds.decimal_odds(home_prob),
            away_decimal_fair=odds.decimal_odds(away_prob),
            exp_goals_home=round(totals.exp_goals_home, 3),
            exp_goals_away=round(totals.exp_goals_away, 3),
            exp_total=round(totals.exp_total, 3),
            fair_total_line=totals.fair_total_line,
            fair_line_p_over=round(totals.fair_line_p_over, 4),
            totals=[contracts.TotalLine(line=line, p_over=round(p, 4)) for line, p in totals.lines],
        ),
        result=result,
    )


# --------------------------------------------------------------------------
# ratings


def team_names() -> dict[str, str]:
    """Abbreviation to full club name, from the stored reference snapshot."""
    try:
        payload = read_snapshot("reference/team")
    except FileNotFoundError:
        return {}
    return {str(row["triCode"]): str(row["fullName"]) for row in payload.get("data", [])}


def build_ratings(
    run: ModelRun,
    season: int,
    generated_at: dt.datetime,
    version: str,
    names: dict[str, str] | None = None,
) -> contracts.Ratings:
    mean = sum(run.ratings.values()) / len(run.ratings) if run.ratings else BASE_RATING
    ordered = sorted(run.ratings.items(), key=lambda kv: kv[1], reverse=True)
    count = len(ordered)

    # Form is measured between two history snapshots, never against the
    # published rating. `run.ratings` has the next season's carryover regression
    # already applied, so differencing it against a pre-regression snapshot
    # makes every strong team look like it is falling and every weak one like it
    # is climbing — an artefact of the rollover, not of anything that happened
    # on the ice.
    recent = run.history[-1][1] if run.history else run.ratings
    week_ago = _ratings_days_back(run, 7)
    labels = names if names is not None else team_names()

    teams: list[contracts.TeamRating] = []
    for rank, (team_id, rating) in enumerate(ordered, start=1):
        abbrev = run.labels.get(team_id, str(team_id))
        teams.append(
            contracts.TeamRating(
                team_id=team_id,
                abbrev=abbrev,
                name=labels.get(abbrev, abbrev),
                elo=round(rating, 1),
                rank=rank,
                percentile=round((count - rank) / (count - 1), 4) if count > 1 else 1.0,
                elo_7d_change=round(recent.get(team_id, rating) - week_ago.get(team_id, rating), 1),
                # Neutral ice against a league-average opponent: the cleanest
                # single number for "how strong is this team".
                win_prob_vs_average=round(expected_score(rating - mean), 4),
            )
        )

    return contracts.Ratings(
        generated_at=generated_at, model_version=version, season=season, teams=teams
    )


def _ratings_days_back(run: ModelRun, days: int) -> dict[int, float]:
    if not run.history:
        return {}
    last_date = run.history[-1][0]
    cutoff = last_date - dt.timedelta(days=days)
    for date, ratings in reversed(run.history):
        if date <= cutoff:
            return ratings
    return run.history[0][1]


def build_rating_history(
    run: ModelRun, games: Sequence[Game], season: int, generated_at: dt.datetime, version: str
) -> contracts.RatingHistory:
    """Daily ratings for one season, which is what the chart draws."""
    season_dates = {g.date_et for g in games if g.season == season}
    points = [
        contracts.RatingPoint(
            date=date,
            elo={
                run.labels.get(team, str(team)): round(rating, 1)
                for team, rating in ratings.items()
            },
        )
        for date, ratings in run.history
        if date in season_dates
    ]
    return contracts.RatingHistory(
        generated_at=generated_at, model_version=version, season=season, points=points
    )


# --------------------------------------------------------------------------
# teams


def build_teams(run: ModelRun, generated_at: dt.datetime, version: str) -> contracts.Teams:
    """Team reference data, from the snapshot the ingest already stored."""
    names = team_names()
    teams = [
        contracts.Team(
            team_id=team_id,
            abbrev=abbrev,
            name=names.get(abbrev, abbrev),
            # Hotlinked. Fine for now; mirror to R2 if the CDN ever objects.
            logo=LOGO_URL.format(abbrev=abbrev),
        )
        for team_id, abbrev in sorted(run.labels.items(), key=lambda kv: kv[1])
    ]
    return contracts.Teams(generated_at=generated_at, model_version=version, teams=teams)


# --------------------------------------------------------------------------
# metrics


def _window_metrics(
    label: str, seasons: Sequence[int], run: ModelRun, games: Sequence[Game]
) -> contracts.WindowMetrics:
    chosen = [p for p in run.elo.values() if is_scorable(p, list(seasons), exclude_no_fans=True)]
    evaluation = metrics_mod.evaluate(
        [p.home_win_prob for p in chosen], [bool(p.home_won) for p in chosen]
    )
    return contracts.WindowMetrics(
        label=label,
        seasons=list(seasons),
        games=evaluation.games,
        log_loss=round(evaluation.log_loss, 5),
        baseline_log_loss=round(evaluation.baseline_log_loss, 5),
        log_loss_skill=round(evaluation.log_loss_skill, 5),
        brier=round(evaluation.brier, 5),
        brier_skill=round(evaluation.brier_skill, 5),
        accuracy=round(evaluation.accuracy, 4),
        baseline_accuracy=round(evaluation.baseline_accuracy, 4),
        worst_calibration_z=round(evaluation.worst_z, 3),
        calibration_threshold=round(evaluation.calibration_threshold, 3),
        well_calibrated=evaluation.well_calibrated,
        calibration=[
            contracts.CalibrationBin(
                lower=b.lower,
                upper=b.upper,
                count=b.count,
                mean_predicted=round(b.mean_predicted, 4),
                observed=round(b.observed, 4),
                z=round(b.z, 3),
            )
            for b in evaluation.calibration
        ],
    )


def _totals_metrics(
    label: str, seasons: Sequence[int], run: ModelRun, games: Sequence[Game]
) -> contracts.TotalsMetrics:
    wanted = set(seasons)
    chosen = [
        p
        for p in run.totals.values()
        if p.scored and p.game_type == config.REGULAR_SEASON and p.season in wanted
    ]
    actuals = [p.actual_total or 0 for p in chosen]
    n = len(chosen)
    if n == 0:
        # An empty window is a legitimate state — a season with no finals yet,
        # or a short run — and must not take the publish job down with it.
        return contracts.TotalsMetrics(
            label=label,
            games=0,
            over_under_hit_rate=0.0,
            model_claimed_rate=0.0,
            total_mae=0.0,
            mean_log_likelihood=0.0,
            modelled_tie_rate=0.0,
            actual_tie_rate=0.0,
        )
    return contracts.TotalsMetrics(
        label=label,
        games=n,
        over_under_hit_rate=round(
            over_under_hit_rate([p.fair_total_line for p in chosen], actuals), 4
        ),
        model_claimed_rate=round(sum(p.fair_line_p_over for p in chosen) / n, 4),
        total_mae=round(total_mae([p.exp_total for p in chosen], actuals), 4),
        mean_log_likelihood=round(mean_log_likelihood(chosen), 5),
        modelled_tie_rate=round(sum(p.tie_probability for p in chosen) / n, 4),
        actual_tie_rate=round(observed_tie_rate(games, list(seasons)), 4),
    )


RECENT_GAMES = 200
"""How many recently graded games the running track record covers."""


def _recent_form(run: ModelRun) -> contracts.RecentForm | None:
    """Rolling performance over the most recently graded games.

    Deliberately not filtered to a season or window — this answers "how is it
    doing lately", which is the question someone opening the page mid-season is
    actually asking.
    """
    graded = sorted(
        (p for p in run.elo.values() if p.scored and p.game_type == config.REGULAR_SEASON),
        key=lambda p: (p.date_et, p.game_id),
    )[-RECENT_GAMES:]
    if not graded:
        return None

    probs = [p.home_win_prob for p in graded]
    outcomes = [bool(p.home_won) for p in graded]
    evaluation = metrics_mod.evaluate(probs, outcomes)

    totals = [run.totals[p.game_id] for p in graded if p.game_id in run.totals]
    actuals = [t.actual_total or 0 for t in totals]

    return contracts.RecentForm(
        games=len(graded),
        since=graded[0].date_et,
        through=graded[-1].date_et,
        log_loss=round(evaluation.log_loss, 5),
        baseline_log_loss=round(evaluation.baseline_log_loss, 5),
        accuracy=round(evaluation.accuracy, 4),
        correct=round(evaluation.accuracy * len(graded)),
        over_under_hit_rate=round(
            over_under_hit_rate([t.fair_total_line for t in totals], actuals), 4
        )
        if totals
        else 0.0,
        total_mae=round(total_mae([t.exp_total for t in totals], actuals), 4) if totals else 0.0,
    )


def build_metrics(
    run: ModelRun,
    games: Sequence[Game],
    holdout: int,
    generated_at: dt.datetime,
    version: str,
) -> contracts.Metrics:
    """The track record the model page publishes, losses included."""
    validation, hold = evaluation_windows(games, holdout)

    by_season: list[contracts.SeasonMetrics] = []
    for season in sorted({p.season for p in run.elo.values()}):
        chosen = [p for p in run.elo.values() if is_scorable(p, [season], exclude_no_fans=True)]
        if len(chosen) < 100:
            continue
        evaluation = metrics_mod.evaluate(
            [p.home_win_prob for p in chosen], [bool(p.home_won) for p in chosen]
        )
        by_season.append(
            contracts.SeasonMetrics(
                season=season,
                games=evaluation.games,
                log_loss=round(evaluation.log_loss, 5),
                baseline_log_loss=round(evaluation.baseline_log_loss, 5),
                accuracy=round(evaluation.accuracy, 4),
            )
        )

    return contracts.Metrics(
        generated_at=generated_at,
        model_version=version,
        holdout_season=holdout,
        recent=_recent_form(run),
        windows=[
            _window_metrics("validation", validation, run, games),
            _window_metrics(f"holdout {config.season_label(holdout)}", hold, run, games),
        ],
        totals=[
            _totals_metrics("validation", validation, run, games),
            _totals_metrics(f"holdout {config.season_label(holdout)}", hold, run, games),
        ],
        by_season=by_season,
    )


# --------------------------------------------------------------------------
# writing


VOLATILE_FIELDS = ("generated_at",)
"""Fields that change on every run without the content changing."""


def _unchanged(existing: str, payload: dict[str, Any]) -> bool:
    """Is the file on disk the same document, ignoring the run timestamp?

    Every document carries a wall-clock stamp, so a naive write dirties all 43
    files on every run. That would commit nightly whether or not anything
    happened, burn a Cloudflare Pages build each time against a 500-a-month
    quota, and make it impossible to tell a real update from a heartbeat.
    """
    try:
        previous = json.loads(existing)
    except json.JSONDecodeError:
        return False
    return {k: v for k, v in previous.items() if k not in VOLATILE_FIELDS} == {
        k: v for k, v in payload.items() if k not in VOLATILE_FIELDS
    }


def _write(path: Path, document: Any) -> tuple[Path, bool]:
    """Write a document, skipping the write when only the timestamp would move.

    Returns the path and whether anything actually changed, so the caller can
    tell a real update from a no-op re-run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json", by_alias=True)

    if path.exists() and _unchanged(path.read_text(encoding="utf-8"), payload):
        return path, False

    path.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return path, True


@dataclass(slots=True)
class PublishReport:
    files: list[Path] = field(default_factory=list)
    changed: list[Path] = field(default_factory=list)
    slates: int = 0
    latest: dt.date | None = None

    def record(self, written: tuple[Path, bool]) -> None:
        path, changed = written
        self.files.append(path)
        if changed:
            self.changed.append(path)


def publish(
    games: Sequence[Game],
    params: ModelParams,
    *,
    today: dt.date | None = None,
    holdout: int = DEFAULT_HOLDOUT,
    out_dir: Path | None = None,
) -> PublishReport:
    """Generate every file under data/v1/."""
    root = out_dir or config.PUBLISH_DIR
    when = dt.datetime.now(dt.UTC).replace(microsecond=0)
    day = today or when.date()
    version = model_version(params)

    run = run_models(games, params)
    by_date: dict[dt.date, list[Game]] = {}
    for game in games:
        by_date.setdefault(game.date_et, []).append(game)

    report = PublishReport()

    dates = slate_dates(games, day)
    entries: list[contracts.IndexEntry] = []
    slates: dict[dt.date, contracts.Slate] = {}
    for date in dates:
        day_games = by_date.get(date, [])
        slate = contracts.Slate(
            generated_at=when,
            model_version=version,
            date=date,
            games=[
                build_slate_game(g, run.elo[g.game_id], run.totals[g.game_id])
                for g in sorted(day_games, key=lambda g: (g.start_utc or when, g.game_id))
            ],
        )
        slates[date] = slate
        entries.append(contracts.IndexEntry(date=date, games=len(slate.games)))
        report.record(_write(root / "slate" / f"{date.isoformat()}.json", slate))
    report.slates = len(dates)

    pointer = latest_date(games, day)
    report.latest = pointer
    if pointer is not None:
        latest = slates.get(pointer)
        if latest is None:
            latest = contracts.Slate(
                generated_at=when,
                model_version=version,
                date=pointer,
                games=[
                    build_slate_game(g, run.elo[g.game_id], run.totals[g.game_id])
                    for g in by_date.get(pointer, [])
                ],
            )
        report.record(_write(root / "latest.json", latest))

    active = max((g.season for g in games if g.is_final), default=holdout)
    report.record(
        _write(root / "ratings" / "current.json", build_ratings(run, active, when, version))
    )
    report.record(
        _write(
            root / "ratings" / "history.json",
            build_rating_history(run, games, active, when, version),
        )
    )
    report.record(_write(root / "teams.json", build_teams(run, when, version)))
    report.record(_write(root / "metrics.json", build_metrics(run, games, holdout, when, version)))
    report.record(
        _write(
            root / "index.json",
            contracts.Index(
                generated_at=when,
                model_version=version,
                latest_date=pointer,
                dates=entries,
            ),
        )
    )
    return report
