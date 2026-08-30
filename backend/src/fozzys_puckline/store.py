"""Persistence: immutable raw snapshots, and the normalized game table."""

from __future__ import annotations

import datetime as dt
import gzip
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import polars as pl

from fozzys_puckline import config
from fozzys_puckline.schemas import Game

# Declared rather than inferred. The two ingest paths carry different columns —
# the bulk backfill has no start time or venue at all — so letting polars infer
# dtypes gives an all-null column a Null type that will not stack with real
# values later. Every write goes through this schema so the table is stable
# whatever the source.
GAME_SCHEMA: dict[str, pl.DataType] = {
    "game_id": pl.Int64(),
    "season": pl.Int64(),
    "game_type": pl.Int64(),
    "date_et": pl.Date(),
    "start_utc": pl.Datetime(time_unit="us", time_zone="UTC"),
    "home_id": pl.Int64(),
    "away_id": pl.Int64(),
    "home_abbrev": pl.Utf8(),
    "away_abbrev": pl.Utf8(),
    "home_score": pl.Int64(),
    "away_score": pl.Int64(),
    "last_period": pl.Utf8(),
    "state": pl.Utf8(),
    "venue": pl.Utf8(),
    "neutral_site": pl.Boolean(),
    "no_fans": pl.Boolean(),
    "divisional_only": pl.Boolean(),
}

GAME_COLUMNS = list(GAME_SCHEMA)


def snapshot_path(key: str, root: Path | None = None) -> Path:
    """`2026/03/01/score` -> data/raw/2026/03/01/score.json.gz"""
    return (root or config.RAW_DIR) / f"{key}.json.gz"


def write_snapshot(key: str, payload: Any, root: Path | None = None) -> Path:
    """Persist a raw API response verbatim, before anything parses it."""
    path = snapshot_path(key, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return path


def read_snapshot(key: str, root: Path | None = None) -> Any:
    """Read a snapshot back, for offline replay after a parser fix."""
    with gzip.open(snapshot_path(key, root), "rt", encoding="utf-8") as handle:
        return json.load(handle)


def games_to_frame(games: Iterable[Game]) -> pl.DataFrame:
    rows = [g.model_dump() for g in games]
    if not rows:
        return empty_frame()
    return pl.DataFrame(rows, schema=GAME_SCHEMA).select(GAME_COLUMNS)


def empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=GAME_SCHEMA)


def frame_to_games(frame: pl.DataFrame) -> list[Game]:
    return [Game.model_validate(row) for row in frame.to_dicts()]


def load_games(path: Path | None = None) -> pl.DataFrame:
    target = path or config.GAMES_PARQUET
    if not target.exists():
        return empty_frame()
    # Cast on read so a table written before a schema change still stacks.
    return pl.read_parquet(target).cast(GAME_SCHEMA)  # type: ignore[arg-type]


def save_games(frame: pl.DataFrame, path: Path | None = None) -> Path:
    target = path or config.GAMES_PARQUET
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.sort(["date_et", "game_id"]).write_parquet(target)
    return target


def upsert_games(new: Iterable[Game], path: Path | None = None) -> pl.DataFrame:
    """Merge rows into the game table, newest write per game_id winning.

    Jobs are re-runnable by design, so this is the operation that makes a
    duplicate cron firing a no-op instead of a corruption.
    """
    incoming = games_to_frame(new)
    if incoming.is_empty():
        return load_games(path)

    existing = load_games(path)
    if existing.is_empty():
        merged = incoming
    else:
        keep = existing.filter(~pl.col("game_id").is_in(incoming["game_id"].to_list()))
        merged = pl.concat([keep.select(GAME_COLUMNS), incoming], how="vertical")

    merged = merged.sort(["date_et", "game_id"])
    save_games(merged, path)
    return merged


def season_counts(frame: pl.DataFrame) -> pl.DataFrame:
    """Games per season and type — the backfill integrity check."""
    if frame.is_empty():
        return pl.DataFrame(schema={"season": pl.Int64, "game_type": pl.Int64, "games": pl.UInt32})
    return (
        frame.group_by(["season", "game_type"])
        .agg(pl.len().alias("games"))
        .sort(["season", "game_type"])
    )


def parse_et_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])
