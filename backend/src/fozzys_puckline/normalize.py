"""Convert raw API payloads into `Game` rows.

Two sources, one output shape:

  bulk   api.nhle.com/stats/rest/en/game  — whole seasons in one request, used
         for backfill. Cheap and exact, but carries no venue or abbreviations,
         so it needs the team reference table.
  score  api-web.nhle.com/v1/score/{date} — one league day, richer, used for the
         nightly results job.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fozzys_puckline.schemas import PERIOD_TO_LAST, Game, GameState, LastPeriod
from fozzys_puckline.seasons import season_flags

JsonDict = dict[str, Any]

FINAL_GAME_STATE_ID = 7

# api-web reports state as a string; anything unrecognized is treated as future
# rather than assumed final, so a new state value can never fabricate a result.
STATE_MAP: dict[str, GameState] = {
    "FUT": "FUT",
    "PRE": "PRE",
    "LIVE": "LIVE",
    "CRIT": "LIVE",
    "OVER": "OFF",
    "FINAL": "FINAL",
    "OFF": "OFF",
}


def _apply_flags(game: Game) -> Game:
    flags = season_flags(game.season, game.game_type, game.date_et)
    return game.model_copy(
        update={
            "no_fans": flags.no_fans,
            "divisional_only": flags.divisional_only,
            # A payload that already says neutral site wins over the season rule.
            "neutral_site": game.neutral_site or flags.neutral_site,
        }
    )


def from_bulk(payload: JsonDict, tricodes: dict[int, str]) -> list[Game]:
    """Rows from the bulk season endpoint."""
    games: list[Game] = []
    for row in payload.get("data", []):
        home_id = int(row["homeTeamId"])
        away_id = int(row["visitingTeamId"])
        is_final = int(row.get("gameStateId", 0)) == FINAL_GAME_STATE_ID

        last_period: LastPeriod | None = None
        if is_final:
            last_period = PERIOD_TO_LAST.get(int(row.get("period", 3)), "REG")

        game = Game(
            game_id=int(row["id"]),
            season=int(row["season"]),
            game_type=int(row["gameType"]),
            date_et=dt.date.fromisoformat(str(row["gameDate"])[:10]),
            start_utc=None,
            home_id=home_id,
            away_id=away_id,
            home_abbrev=tricodes.get(home_id, str(home_id)),
            away_abbrev=tricodes.get(away_id, str(away_id)),
            home_score=int(row["homeScore"]) if is_final else None,
            away_score=int(row["visitingScore"]) if is_final else None,
            last_period=last_period,
            state="FINAL" if is_final else "FUT",
        )
        games.append(_apply_flags(game))
    return games


def _team_block(block: JsonDict) -> tuple[int, str, int | None]:
    score = block.get("score")
    return int(block["id"]), str(block["abbrev"]), None if score is None else int(score)


def from_schedule(payload: JsonDict) -> list[Game]:
    """Rows from api-web /schedule, which covers a game week.

    The bulk season endpoint used for backfill carries no start time and no
    venue, so upcoming games arrive from it as a bare skeleton. This is what
    fills those in — without it the slate cannot show a puck-drop time, which is
    most of what a matchup card is for.

    The date lives on the game-week entry rather than on each game, so it is
    threaded down here.
    """
    games: list[Game] = []
    for day in payload.get("gameWeek", []):
        date_et = dt.date.fromisoformat(str(day["date"])[:10])
        for row in day.get("games", []):
            games.append(_from_web_game(row, date_et))
    return games


def _from_web_game(row: JsonDict, date_et: dt.date) -> Game:
    """Shared parser for the api-web game shape, used by score and schedule."""
    home_id, home_abbrev, home_score = _team_block(row["homeTeam"])
    away_id, away_abbrev, away_score = _team_block(row["awayTeam"])

    state = STATE_MAP.get(str(row.get("gameState", "")), "FUT")

    last_period: LastPeriod | None = None
    raw_last = (row.get("gameOutcome") or {}).get("lastPeriodType")
    if raw_last in ("REG", "OT", "SO"):
        last_period = raw_last

    start_raw = row.get("startTimeUTC")
    start_utc = (
        dt.datetime.fromisoformat(str(start_raw).replace("Z", "+00:00")) if start_raw else None
    )

    game = Game(
        game_id=int(row["id"]),
        season=int(row["season"]),
        game_type=int(row["gameType"]),
        date_et=date_et,
        start_utc=start_utc,
        home_id=home_id,
        away_id=away_id,
        home_abbrev=home_abbrev,
        away_abbrev=away_abbrev,
        home_score=home_score,
        away_score=away_score,
        last_period=last_period,
        state=state,
        venue=(row.get("venue") or {}).get("default"),
        neutral_site=bool(row.get("neutralSite", False)),
    )
    return _apply_flags(game)


def from_score(payload: JsonDict) -> list[Game]:
    """Rows from one day of api-web /score."""
    games: list[Game] = []
    for row in payload.get("games", []):
        home_id, home_abbrev, home_score = _team_block(row["homeTeam"])
        away_id, away_abbrev, away_score = _team_block(row["awayTeam"])

        state = STATE_MAP.get(str(row.get("gameState", "")), "FUT")

        last_period: LastPeriod | None = None
        outcome = row.get("gameOutcome") or {}
        raw_last = outcome.get("lastPeriodType")
        if raw_last in ("REG", "OT", "SO"):
            last_period = raw_last

        start_raw = row.get("startTimeUTC")
        start_utc = (
            dt.datetime.fromisoformat(str(start_raw).replace("Z", "+00:00")) if start_raw else None
        )

        venue = (row.get("venue") or {}).get("default")

        game = Game(
            game_id=int(row["id"]),
            season=int(row["season"]),
            game_type=int(row["gameType"]),
            date_et=dt.date.fromisoformat(str(row["gameDate"])[:10]),
            start_utc=start_utc,
            home_id=home_id,
            away_id=away_id,
            home_abbrev=home_abbrev,
            away_abbrev=away_abbrev,
            home_score=home_score,
            away_score=away_score,
            last_period=last_period,
            state=state,
            venue=venue,
            neutral_site=bool(row.get("neutralSite", False)),
        )
        games.append(_apply_flags(game))
    return games
