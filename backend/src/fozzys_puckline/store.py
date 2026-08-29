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

GAME_COLUMNS = [
    "game_id",
    "season",
    "game_type",
    "date_et",
    "start_utc",
    "home_id",
    "away_id",
    "home_abbrev",
    "away_abbrev",
    "home_score",
    "away_score",
    "last_period",
    "state",
    "venue",
    "neutral_site",
    "no_fans",
    "divisional_only",
]


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
        return pl.DataFrame(schema={c: pl.Null for c in GAME_COLUMNS})
    return pl.DataFrame(rows).select(GAME_COLUMNS)


def frame_to_games(frame: pl.DataFrame) -> list[Game]:
    return [Game.model_validate(row) for row in frame.to_dicts()]


def load_games(path: Path | None = None) -> pl.DataFrame:
    target = path or config.GAMES_PARQUET
    if not target.exists():
        return pl.DataFrame(schema={c: pl.Null for c in GAME_COLUMNS})
    return pl.read_parquet(target)


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
