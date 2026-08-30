"""Command line entry points. `uv run puckline --help`."""

from __future__ import annotations

import datetime as dt
import math

import typer

from fozzys_puckline import backtest as bt
from fozzys_puckline import config, pipeline, store
from fozzys_puckline.calibrate import calibrate, match_tie_marginal, observed_tie_rate
from fozzys_puckline.fit import fit as run_fit
from fozzys_puckline.goals import over_under_hit_rate, total_mae
from fozzys_puckline.identity import rating_key
from fozzys_puckline.metrics import Evaluation
from fozzys_puckline.params import FITTED_FIELDS, EloParams, ModelParams, load_params
from fozzys_puckline.sources.nhl_api import NhlApi
from fozzys_puckline.totals import TotalsEngine, mean_log_likelihood

app = typer.Typer(
    add_completion=False,
    help="Fozzy's Puckline — NHL ingest, ratings, and predictions.",
)


@app.command()
def backfill(
    start: int = typer.Option(config.FIRST_SEASON, help="First season id, e.g. 20152016."),
    end: int = typer.Option(0, help="Last season id. Defaults to the current season."),
    playoffs: bool = typer.Option(True, help="Include playoff games."),
    dry_run: bool = typer.Option(False, help="Fetch and check, but do not write the table."),
) -> None:
    """Rebuild the game table from the bulk season endpoint."""
    last = end or pipeline.current_season(dt.date.today())
    seasons = pipeline.seasons_between(start, last)
    game_types = config.GAME_TYPES if playoffs else (config.REGULAR_SEASON,)

    typer.echo(
        f"Backfilling {config.season_label(seasons[0])} .. {config.season_label(seasons[-1])}"
    )

    with NhlApi() as api:
        result = pipeline.backfill(api, seasons, game_types)
        requests_made = api.requests_made

    for report in result.reports:
        label = config.season_label(report.season)
        kind = "reg" if report.game_type == config.REGULAR_SEASON else "post"
        mark = "ok " if report.ok else "BAD"
        detail = f"{report.parsed:>5} parsed / {report.api_total:>5} claimed"
        if report.expected is not None:
            verdict = "match" if report.matches_reference else f"expected {report.expected}"
            detail += f"  ({verdict})"
        typer.echo(f"  [{mark}] {label} {kind:<4} {detail}")

    typer.echo(f"{len(result.games)} games, {requests_made} requests")

    if dry_run:
        typer.echo("dry run — nothing written")
    else:
        frame = pipeline.persist(result.games)
        typer.echo(f"wrote {frame.height} rows to {config.GAMES_PARQUET}")

    if not result.ok:
        raise typer.Exit(code=1)


@app.command("ingest-day")
def ingest_day(
    date: str = typer.Argument("", help="League day as YYYY-MM-DD. Defaults to yesterday."),
) -> None:
    """Pull one league day of results and merge it into the game table."""
    target = dt.date.fromisoformat(date) if date else dt.date.today() - dt.timedelta(days=1)

    with NhlApi() as api:
        games = pipeline.ingest_day(api, target)

    finals = sum(1 for g in games if g.is_final)
    frame = pipeline.persist(games)
    typer.echo(f"{target}: {len(games)} games ({finals} final) — table now {frame.height} rows")


@app.command()
def stats() -> None:
    """Row counts per season, for eyeballing table health."""
    frame = store.load_games()
    if frame.is_empty():
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    for row in store.season_counts(frame).to_dicts():
        kind = "reg" if row["game_type"] == config.REGULAR_SEASON else "post"
        typer.echo(f"  {config.season_label(row['season'])} {kind:<4} {row['games']:>5}")
    typer.echo(f"{frame.height} rows total")


def _report(label: str, evaluation: Evaluation) -> None:
    e = evaluation
    verdict = "beats baseline" if e.beats_baseline else "LOSES TO BASELINE"
    calib = "calibrated" if e.well_calibrated else "MISCALIBRATED"
    typer.echo(f"\n{label}  n={e.games}")
    typer.echo(
        f"  log loss {e.log_loss:.5f}  baseline {e.baseline_log_loss:.5f}"
        f"  skill {e.log_loss_skill:+.4f}  ({verdict})"
    )
    typer.echo(f"  brier    {e.brier:.5f}  skill {e.brier_skill:+.4f}")
    typer.echo(f"  accuracy {e.accuracy:.4f}  baseline {e.baseline_accuracy:.4f}")
    typer.echo(
        f"  calibration: worst bin {e.worst_z:.2f} sigma over {e.tested_bins} bins,"
        f" threshold {e.calibration_threshold:.2f} ({calib})"
    )


@app.command()
def backtest(
    holdout: int = typer.Option(bt.DEFAULT_HOLDOUT, help="Season held out of fitting."),
    validation: bool = typer.Option(True, help="Also report the validation window."),
) -> None:
    """Score the current params.json walk-forward."""
    games = bt.load_ordered_games()
    if not games:
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    params = EloParams.from_json()
    valid, hold = bt.evaluation_windows(games, holdout)

    if validation:
        _report("VALIDATION", bt.run(games, params, eval_seasons=valid).evaluation)
    result = bt.run(games, params, eval_seasons=hold)
    _report(f"HOLDOUT {config.season_label(holdout)}", result.evaluation)

    if not result.evaluation.beats_baseline:
        raise typer.Exit(code=1)


@app.command()
def fit(
    holdout: int = typer.Option(bt.DEFAULT_HOLDOUT, help="Season kept out of the search."),
    rounds: int = typer.Option(4, help="Coordinate-descent passes."),
    write: bool = typer.Option(False, help="Write the result to params.json."),
) -> None:
    """Fit parameters on the validation window. Never touches the holdout."""
    games = bt.load_ordered_games()
    if not games:
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    valid, hold = bt.evaluation_windows(games, holdout)
    typer.echo(f"fitting on {config.season_label(valid[0])} .. {config.season_label(valid[-1])}")

    result = run_fit(games, valid, rounds=rounds)
    typer.echo(f"{result.evaluations} evaluations")
    for name in FITTED_FIELDS:
        typer.echo(f"  {name:<12} {getattr(result.params, name)}")

    _report("VALIDATION", bt.run(games, result.params, eval_seasons=valid).evaluation)
    _report(
        f"HOLDOUT {config.season_label(holdout)}",
        bt.run(games, result.params, eval_seasons=hold).evaluation,
    )

    if write:
        typer.echo(
            f"\nwrote {ModelParams(elo=result.params, totals=load_params().totals).to_json()}"
        )
    else:
        typer.echo("\nnot written — pass --write to save to params.json")


@app.command()
def rate(top: int = typer.Option(10, help="How many teams to show.")) -> None:
    """Current Elo ratings from the full game history."""
    games = bt.load_ordered_games()
    if not games:
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    result = bt.run(games, EloParams.from_json(), eval_seasons=None, keep_predictions=False)

    # Rating keys are team ids. Label them from the most recent game each club
    # played, which also gives clubs that changed id their current name.
    names: dict[int, str] = {}
    for game in games:
        names[rating_key(game.home_id)] = game.home_abbrev
        names[rating_key(game.away_id)] = game.away_abbrev

    ranked = sorted(result.ratings.items(), key=lambda kv: kv[1], reverse=True)
    for rank, (team, rating) in enumerate(ranked[:top], start=1):
        typer.echo(f"  {rank:>2}. {names.get(team, str(team)):<4} {rating:>7.1f}")


@app.command("calibrate-totals")
def calibrate_totals(
    holdout: int = typer.Option(bt.DEFAULT_HOLDOUT, help="Season kept out of estimation."),
    write: bool = typer.Option(False, help="Write the result to params.json."),
) -> None:
    """Measure the goal-model constants on the validation seasons only."""
    games = bt.load_ordered_games()
    if not games:
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    valid, _ = bt.evaluation_windows(games, holdout)
    typer.echo(f"measuring on {config.season_label(valid[0])} .. {config.season_label(valid[-1])}")

    constants = calibrate(games, valid)
    params = load_params().totals.replace(
        league_goals=constants.league_goals,
        home_share=constants.home_share,
        dispersion=constants.dispersion,
        tie_intercept=constants.tie_intercept,
        tie_slope=constants.tie_slope,
    )
    typer.echo(f"  from {constants.games} games")
    for name in ("league_goals", "home_share", "dispersion", "tie_slope"):
        typer.echo(f"  {name:<14} {getattr(constants, name)}")

    typer.echo("  matching the marginal tie rate...")
    params = match_tie_marginal(games, valid, params)
    typer.echo(f"  tie_intercept  {constants.tie_intercept} -> {params.tie_intercept}")

    if write:
        target = ModelParams(elo=load_params().elo, totals=params).to_json()
        typer.echo(f"wrote {target}")
    else:
        typer.echo("not written — pass --write to save to params.json")


@app.command("backtest-totals")
def backtest_totals(
    holdout: int = typer.Option(bt.DEFAULT_HOLDOUT, help="Season held out of fitting."),
) -> None:
    """Score the goal model walk-forward."""
    games = bt.load_ordered_games()
    if not games:
        typer.echo("game table is empty — run `puckline backfill`")
        raise typer.Exit(code=1)

    params = load_params().totals
    valid, hold = bt.evaluation_windows(games, holdout)
    predictions = list(TotalsEngine(params=params).run(games))

    passed = True
    for label, seasons in (
        ("VALIDATION", valid),
        (f"HOLDOUT {config.season_label(holdout)}", hold),
    ):
        chosen = [
            p
            for p in predictions
            if p.scored and p.game_type == config.REGULAR_SEASON and p.season in seasons
        ]
        n = len(chosen)
        lines = [p.fair_total_line for p in chosen]
        actuals = [p.actual_total or 0 for p in chosen]
        hit = over_under_hit_rate(lines, actuals)
        claimed = sum(p.fair_line_p_over for p in chosen) / n
        sigma = math.sqrt(0.25 / n)
        in_gate = 0.48 <= hit <= 0.52
        passed = passed and in_gate

        typer.echo(f"\n{label}  n={n}")
        typer.echo(
            f"  over/under at the fair line {hit:.4f}"
            f"   model claims {claimed:.4f}   {abs(hit - claimed) / sigma:.2f} sigma"
            f"   {'in gate' if in_gate else 'OUT OF GATE (.48-.52)'}"
        )
        typer.echo(f"  total MAE {total_mae([p.exp_total for p in chosen], actuals):.4f}")
        typer.echo(f"  mean log likelihood {mean_log_likelihood(chosen):.5f}")
        typer.echo(
            f"  P(past regulation): model {sum(p.tie_probability for p in chosen) / n:.4f}"
            f"   actual {observed_tie_rate(games, seasons):.4f}"
        )

    if not passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
