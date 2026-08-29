"""Command line entry points. `uv run puckline --help`."""

from __future__ import annotations

import datetime as dt

import typer

from fozzys_puckline import config, pipeline, store
from fozzys_puckline.sources.nhl_api import NhlApi

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


if __name__ == "__main__":
    app()
