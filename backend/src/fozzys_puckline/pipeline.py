"""Ingest orchestration. Thin enough to test, so the CLI stays a shell."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import polars as pl

from fozzys_puckline import config, normalize, store
from fozzys_puckline.schemas import Game
from fozzys_puckline.sources.nhl_api import NhlApi, team_tricodes

# Reference counts for full seasons, used as an integrity check on backfill.
# 2015-16 (1230) and 2024-25 (1312) were verified directly against the API.
# 2019-20 was cut short by the pause; 2020-21 was a 56-game season.
EXPECTED_REGULAR_SEASON_GAMES: dict[int, int] = {
    20152016: 1230,
    20162017: 1230,
    20172018: 1271,
    20182019: 1271,
    20192020: 1082,
    20202021: 868,
    20212022: 1312,
    20222023: 1312,
    20232024: 1312,
    20242025: 1312,
    20252026: 1312,
    # The league moved to an 84-game schedule in 2026-27: 32 * 84 / 2.
    20262027: 1344,
}

# Playoff counts are scheduled slots, not games played. The API keeps rows for
# series games that never happened (a sweep still lists games 5 through 7), so a
# season reports ~105 playoff rows of which only ~85 reach a final state. Those
# placeholders stay `FUT` forever and are filtered by `Game.is_final`, which is
# why playoff seasons get no reference count.


@dataclass(slots=True)
class SeasonReport:
    """What one season of backfill produced, and whether it looks right."""

    season: int
    game_type: int
    api_total: int
    parsed: int
    expected: int | None = None

    @property
    def parses_cleanly(self) -> bool:
        """Did we turn every row the API claimed into a game?"""
        return self.api_total == self.parsed

    @property
    def matches_reference(self) -> bool | None:
        if self.expected is None:
            return None
        return self.parsed == self.expected

    @property
    def ok(self) -> bool:
        return self.parses_cleanly and self.matches_reference is not False


@dataclass(slots=True)
class BackfillResult:
    games: list[Game] = field(default_factory=list)
    reports: list[SeasonReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.reports)


def backfill(
    api: NhlApi,
    seasons: list[int],
    game_types: tuple[int, ...] = config.GAME_TYPES,
) -> BackfillResult:
    """Pull whole seasons from the bulk endpoint.

    One request per season/type plus one for the team table, so a decade costs
    about twenty requests rather than two thousand date-by-date calls.
    """
    tricodes = team_tricodes(api.teams())
    result = BackfillResult()

    for season in seasons:
        for game_type in game_types:
            payload = api.season_games(season, game_type)
            games = normalize.from_bulk(payload, tricodes)
            result.games.extend(games)
            result.reports.append(
                SeasonReport(
                    season=season,
                    game_type=game_type,
                    api_total=int(payload.get("total", 0)),
                    parsed=len(games),
                    expected=(
                        EXPECTED_REGULAR_SEASON_GAMES.get(season)
                        if game_type == config.REGULAR_SEASON
                        else None
                    ),
                )
            )

    return result


def ingest_day(api: NhlApi, date_et: dt.date) -> list[Game]:
    """One league day of results from the richer /score endpoint."""
    return normalize.from_score(api.score(date_et))


def ingest_schedule(api: NhlApi, start: dt.date, weeks: int = 2) -> list[Game]:
    """Upcoming games, with start times and venues.

    The bulk season endpoint that drives backfill carries neither, so upcoming
    games land in the table as a skeleton and the slate has no puck-drop time to
    show. `/schedule` returns a whole game week per request, so a fortnight
    costs two calls.
    """
    games: list[Game] = []
    for week in range(weeks):
        games.extend(normalize.from_schedule(api.schedule(start + dt.timedelta(weeks=week))))
    return games


def seasons_between(first: int, last: int) -> list[int]:
    """Inclusive list of season ids, e.g. 20152016 .. 20172018."""
    start = config.season_start_year(first)
    end = config.season_start_year(last)
    return [config.season_id(y) for y in range(start, end + 1)]


def current_season(today: dt.date) -> int:
    """NHL seasons are labelled by the year they start in; July is the rollover."""
    start_year = today.year if today.month >= 7 else today.year - 1
    return config.season_id(start_year)


def persist(games: list[Game]) -> pl.DataFrame:
    return store.upsert_games(games)
