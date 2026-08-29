"""Paths and constants. Every tunable lives here or in params.json, never inline."""

from __future__ import annotations

from pathlib import Path

# backend/src/fozzys_puckline/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
GAMES_PARQUET = DATA_DIR / "games.parquet"
PUBLISH_DIR = REPO_ROOT / "web" / "public" / "data" / "v1"

# --- API bases -------------------------------------------------------------
WEB_API = "https://api-web.nhle.com/v1"
STATS_API = "https://api.nhle.com/stats/rest/en"

USER_AGENT = "fozzys-puckline/0.1 (+https://github.com/AjFroster/fozzys-puckline)"

# --- ingest window ---------------------------------------------------------
# Decision: backfill from 2015-16 forward. Tightest match to the modern sport;
# see docs/METHODOLOGY.md for the sample-size tradeoffs this creates.
FIRST_SEASON = 20152016

REGULAR_SEASON = 2
PLAYOFFS = 3
GAME_TYPES = (REGULAR_SEASON, PLAYOFFS)

# --- client behaviour ------------------------------------------------------
THROTTLE_SECONDS = 0.4
MAX_RETRIES = 5
BACKOFF_BASE = 1.5
REQUEST_TIMEOUT = 30.0
# Hard ceiling per process so a bug cannot hammer an unofficial public API.
MAX_REQUESTS_PER_RUN = 2000


def season_id(start_year: int) -> int:
    """2015 -> 20152016."""
    return start_year * 10000 + (start_year + 1)


def season_start_year(season: int) -> int:
    """20152016 -> 2015."""
    return season // 10000


def season_label(season: int) -> str:
    """20152016 -> '2015-16'."""
    start = season_start_year(season)
    return f"{start}-{str(start + 1)[2:]}"
