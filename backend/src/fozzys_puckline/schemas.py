"""Normalized internal models.

These are the shape everything downstream reads. Both ingest paths (the bulk
season endpoint and the daily score endpoint) converge here, so the Elo engine
never learns which source a row came from.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

LastPeriod = Literal["REG", "OT", "SO"]
GameState = Literal["FUT", "PRE", "LIVE", "OFF", "FINAL"]

FINAL_STATES: frozenset[str] = frozenset({"OFF", "FINAL"})

# `period` on the bulk stats endpoint, verified against 2015-16:
# 3 -> 955 games, 4 -> 168, 5 -> 107 (22.4% past regulation).
PERIOD_TO_LAST: dict[int, LastPeriod] = {3: "REG", 4: "OT", 5: "SO"}


class Game(BaseModel):
    """One NHL game, normalized."""

    game_id: int
    season: int
    game_type: int
    date_et: dt.date = Field(description="League day, not the UTC day.")
    start_utc: dt.datetime | None = None

    home_id: int
    away_id: int
    home_abbrev: str
    away_abbrev: str

    home_score: int | None = None
    away_score: int | None = None
    last_period: LastPeriod | None = None
    state: GameState = "FUT"

    venue: str | None = None

    # Context flags, from seasons.season_flags.
    neutral_site: bool = False
    no_fans: bool = False
    divisional_only: bool = False

    @property
    def is_final(self) -> bool:
        return self.state in FINAL_STATES and self.home_score is not None

    @property
    def total_goals(self) -> int | None:
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score + self.away_score

    @property
    def home_won(self) -> bool | None:
        """None until final. Ties do not exist in the modern NHL."""
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        return self.home_score > self.away_score

    @property
    def went_past_regulation(self) -> bool:
        return self.last_period in ("OT", "SO")

    @property
    def regulation_scores(self) -> tuple[int, int] | None:
        """Goals at the end of regulation, exactly recoverable from the final.

        An overtime or shootout winner is credited exactly one goal, and getting
        there requires regulation to have been tied. So removing that goal from
        the winner reconstructs regulation without ambiguity. Verified against
        all 14,508 finals in the backfill: every reconstruction comes out tied,
        and none goes negative.

        This matters because book totals settle on the *final* score including
        overtime and the shootout, while goal rates have to be estimated on
        regulation. Estimating rates on final scores instead would fold the OT
        goal into every team's attack rate and quietly inflate every total.
        """
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        if not self.went_past_regulation:
            return self.home_score, self.away_score
        if self.home_score > self.away_score:
            return self.home_score - 1, self.away_score
        return self.home_score, self.away_score - 1
