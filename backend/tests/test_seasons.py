"""The anomalous-season flags decide what the home-ice fit is allowed to see."""

from __future__ import annotations

import datetime as dt

from fozzys_puckline.seasons import season_flags


def test_normal_season_is_unflagged() -> None:
    flags = season_flags(20232024, 2, dt.date(2024, 1, 15))
    assert flags == season_flags(20152016, 2, dt.date(2015, 10, 7))
    assert not flags.no_fans
    assert not flags.neutral_site
    assert not flags.divisional_only
    assert flags.usable_for_hfa_fit


def test_2019_20_regular_season_had_crowds() -> None:
    flags = season_flags(20192020, 2, dt.date(2020, 1, 20))
    assert not flags.no_fans
    assert flags.usable_for_hfa_fit


def test_2019_20_bubble_is_neutral_and_empty() -> None:
    flags = season_flags(20192020, 3, dt.date(2020, 8, 11))
    assert flags.no_fans
    assert flags.neutral_site
    assert not flags.usable_for_hfa_fit


def test_2020_21_regular_season_is_empty_and_divisional() -> None:
    flags = season_flags(20202021, 2, dt.date(2021, 3, 1))
    assert flags.no_fans
    assert flags.divisional_only
    assert not flags.usable_for_hfa_fit


def test_2020_21_playoffs_are_empty_but_not_divisional_only() -> None:
    flags = season_flags(20202021, 3, dt.date(2021, 6, 1))
    assert flags.no_fans
    assert not flags.divisional_only
