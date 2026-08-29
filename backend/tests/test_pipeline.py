from __future__ import annotations

import datetime as dt

from fozzys_puckline import config
from fozzys_puckline.pipeline import SeasonReport, current_season, seasons_between


def test_seasons_between_is_inclusive() -> None:
    assert seasons_between(20152016, 20172018) == [20152016, 20162017, 20172018]


def test_seasons_between_single_season() -> None:
    assert seasons_between(20242025, 20242025) == [20242025]


def test_current_season_rolls_over_in_july() -> None:
    assert current_season(dt.date(2026, 6, 30)) == 20252026
    assert current_season(dt.date(2026, 7, 1)) == 20262027
    assert current_season(dt.date(2026, 10, 8)) == 20262027


def test_season_label() -> None:
    assert config.season_label(20152016) == "2015-16"
    assert config.season_label(20242025) == "2024-25"


def test_report_is_ok_when_counts_line_up() -> None:
    report = SeasonReport(season=20152016, game_type=2, api_total=1230, parsed=1230, expected=1230)
    assert report.parses_cleanly
    assert report.matches_reference
    assert report.ok


def test_report_flags_a_dropped_row() -> None:
    """The API claiming more rows than we parsed means a schema change."""
    report = SeasonReport(season=20152016, game_type=2, api_total=1230, parsed=1229, expected=1230)
    assert not report.parses_cleanly
    assert not report.ok


def test_report_without_reference_still_passes() -> None:
    """Playoff rounds have no fixed game count, so only the parse check applies."""
    report = SeasonReport(season=20152016, game_type=3, api_total=87, parsed=87)
    assert report.matches_reference is None
    assert report.ok
