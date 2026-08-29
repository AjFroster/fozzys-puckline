"""Both ingest paths must converge on identical row semantics."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fozzys_puckline import normalize
from fozzys_puckline.sources.nhl_api import team_tricodes


def test_bulk_maps_period_to_last_period(
    bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    games = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))

    assert [g.last_period for g in games] == ["REG", "OT", "SO"]
    assert [g.went_past_regulation for g in games] == [False, True, True]


def test_bulk_resolves_abbreviations(
    bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    first = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))[0]

    assert first.game_id == 2015020001
    assert first.home_abbrev == "TOR"
    assert first.away_abbrev == "MTL"
    assert first.date_et == dt.date(2015, 10, 7)
    assert first.is_final
    assert first.home_won is False
    assert first.total_goals == 4


def test_bulk_falls_back_to_team_id_when_tricode_unknown(
    bulk_payload: dict[str, Any],
) -> None:
    games = normalize.from_bulk(bulk_payload, {})
    assert games[0].home_abbrev == "10"


def test_score_reads_outcome_and_venue(score_payload: dict[str, Any]) -> None:
    games = normalize.from_score(score_payload)
    game = games[0]

    assert game.state == "OFF"
    assert game.is_final
    assert game.last_period == "REG"
    assert game.venue == "PPG Paints Arena"
    assert game.home_abbrev == "PIT"
    assert game.away_abbrev == "VGK"
    assert game.start_utc is not None
    assert game.start_utc.tzinfo is not None


def test_unknown_state_never_fabricates_a_final(score_payload: dict[str, Any]) -> None:
    payload = {"games": [dict(score_payload["games"][0], gameState="SOMETHING_NEW")]}

    game = normalize.from_score(payload)[0]

    assert game.state == "FUT"
    assert not game.is_final
    assert game.home_won is None


def test_flags_are_applied_during_normalization(score_payload: dict[str, Any]) -> None:
    row = dict(score_payload["games"][0], season=20202021, gameDate="2021-03-01")
    game = normalize.from_score({"games": [row]})

    assert game[0].no_fans
    assert game[0].divisional_only
