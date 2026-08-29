"""Anomalous-season flags.

The 2015-16-forward backfill window is ~10 seasons, two of which are not normal
hockey. Flagging them at ingest is what lets the rating fit exclude them later
instead of silently averaging them in:

  2019-20  Paused 2020-03-11. The regular season was played in front of crowds;
           the restart from 2020-08-01 was a neutral-site, no-crowd bubble.
  2020-21  56 games, four temporary divisions with no cross-division play, and
           overwhelmingly empty buildings. A handful of teams admitted limited
           crowds late in the season; we do not model that partial exception,
           so `no_fans` is a deliberate slight over-count for this season.

Empty buildings measurably suppress home advantage. Measured over the backfill
window: home teams won 53.96% of 13,426 games with a crowd, against 52.50% of
1,082 games without one. That is roughly half the edge, not none of it -- but a
1.5-point bias is large at this sample size, so any game flagged `no_fans` is
excluded from the home-ice fit rather than averaged in.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

SEASON_2019_20 = 20192020
SEASON_2020_21 = 20202021

# First day of the 2019-20 qualifying round inside the Edmonton/Toronto bubble.
BUBBLE_START = dt.date(2020, 8, 1)


@dataclass(frozen=True, slots=True)
class SeasonFlags:
    """Context flags that make a game unrepresentative of normal conditions."""

    no_fans: bool
    neutral_site: bool
    divisional_only: bool

    @property
    def usable_for_hfa_fit(self) -> bool:
        return not (self.no_fans or self.neutral_site)


NORMAL = SeasonFlags(no_fans=False, neutral_site=False, divisional_only=False)


def season_flags(season: int, game_type: int, date_et: dt.date) -> SeasonFlags:
    """Flags for one game. Pure function of season, type, and league day."""
    if season == SEASON_2019_20 and date_et >= BUBBLE_START:
        return SeasonFlags(no_fans=True, neutral_site=True, divisional_only=False)

    if season == SEASON_2020_21:
        # Divisional-only applies to the regular season; the playoffs used a
        # bracket that opened up after the divisional rounds.
        return SeasonFlags(
            no_fans=True,
            neutral_site=False,
            divisional_only=(game_type == 2),
        )

    return NORMAL
