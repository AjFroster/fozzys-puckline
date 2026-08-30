"""The Elo rating engine.

Deliberately simple and interpretable: the site exposes ratings as a first-class
feature, and an opaque rating is a worse product than a slightly less accurate
transparent one.

Ratings are strictly walk-forward. `run` yields a prediction for every game
*before* applying that game's result, so nothing downstream can accidentally
evaluate the model on information it did not have.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from fozzys_puckline.identity import rating_key
from fozzys_puckline.params import BASE_RATING, EloParams
from fozzys_puckline.schemas import Game


@dataclass(frozen=True, slots=True)
class GamePrediction:
    """What the model believed before a game, and what happened."""

    game_id: int
    season: int
    game_type: int
    date_et: dt.date
    home_abbrev: str
    away_abbrev: str
    home_elo_pre: float
    away_elo_pre: float
    hfa_applied: float
    home_b2b: bool
    away_b2b: bool
    home_rest_days: int | None
    away_rest_days: int | None
    home_win_prob: float
    home_won: bool | None
    no_fans: bool
    neutral_site: bool

    @property
    def scored(self) -> bool:
        """Only finals can be evaluated."""
        return self.home_won is not None


def expected_score(diff: float) -> float:
    """Standard Elo expectation from a rating difference."""
    return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))


def mov_multiplier(goal_diff: int, winner_diff: float, mov_const: float) -> float:
    """Margin-of-victory scaling, autocorrelation-corrected.

    The second term shrinks the update when a heavy favourite wins big, which is
    what stops strong teams from running away with the rating scale.
    """
    return math.log(abs(goal_diff) + 1.0) * (mov_const / (0.001 * winner_diff + mov_const))


@dataclass(slots=True)
class EloEngine:
    """Walk-forward rating state.

    Not reusable across runs: build a fresh engine per backtest so a previous
    sweep's ratings can never leak into the next one.
    """

    params: EloParams = field(default_factory=EloParams)
    ratings: dict[int, float] = field(default_factory=dict)
    _last_played: dict[int, dt.date] = field(default_factory=dict, repr=False)
    _season: int | None = field(default=None, repr=False)
    _seeded: bool = field(default=False, repr=False)

    # -- rating access -----------------------------------------------------

    def rating(self, team_id: int) -> float:
        return self.ratings[rating_key(team_id)]

    def league_mean(self) -> float:
        if not self.ratings:
            return BASE_RATING
        return sum(self.ratings.values()) / len(self.ratings)

    def _ensure_rated(self, team_id: int) -> None:
        key = rating_key(team_id)
        if key in self.ratings:
            return
        # Everyone present in the first season processed starts level; a club
        # appearing later is genuinely new and starts below the pack.
        self.ratings[key] = BASE_RATING if not self._seeded else self.params.expansion_init

    # -- season boundaries -------------------------------------------------

    def _roll_season(self, season: int) -> None:
        """Regress toward the league mean between seasons.

        Regressing to the mean rather than to a fixed 1500 keeps the system
        conservative: updates are zero-sum, and adding an expansion club below
        1500 pulls the mean down, so a fixed anchor would quietly inject rating
        into the pool every autumn.
        """
        if self._season is None:
            self._season = season
            return
        if season == self._season:
            return

        mean = self.league_mean()
        c = self.params.carryover
        self.ratings = {team: c * value + (1.0 - c) * mean for team, value in self.ratings.items()}
        self._season = season
        self._seeded = True
        self._last_played.clear()

    # -- prediction --------------------------------------------------------

    def _rest(self, team_id: int, date_et: dt.date) -> tuple[int | None, bool]:
        last = self._last_played.get(rating_key(team_id))
        if last is None:
            return None, False
        days = (date_et - last).days
        return days, days <= 1

    def _hfa_for(self, game: Game) -> float:
        if game.neutral_site:
            return 0.0
        if game.no_fans:
            return self.params.hfa * self.params.no_fans_hfa_factor
        return self.params.hfa

    def predict(self, game: Game) -> GamePrediction:
        """Pregame view. Pure — calling this never changes rating state."""
        self._ensure_rated(game.home_id)
        self._ensure_rated(game.away_id)

        home_elo = self.rating(game.home_id)
        away_elo = self.rating(game.away_id)

        home_rest, home_b2b = self._rest(game.home_id, game.date_et)
        away_rest, away_b2b = self._rest(game.away_id, game.date_et)

        # Fatigue is a pregame adjustment to the difference, never to the
        # stored rating: a tired team is temporarily worse, not worse.
        adj = 0.0
        if home_b2b:
            adj -= self.params.b2b_penalty
        if away_b2b:
            adj += self.params.b2b_penalty

        hfa = self._hfa_for(game)
        diff = home_elo + hfa + adj - away_elo

        return GamePrediction(
            game_id=game.game_id,
            season=game.season,
            game_type=game.game_type,
            date_et=game.date_et,
            home_abbrev=game.home_abbrev,
            away_abbrev=game.away_abbrev,
            home_elo_pre=home_elo,
            away_elo_pre=away_elo,
            hfa_applied=hfa,
            home_b2b=home_b2b,
            away_b2b=away_b2b,
            home_rest_days=home_rest,
            away_rest_days=away_rest,
            home_win_prob=expected_score(diff * self.params.diff_scale),
            home_won=game.home_won,
            no_fans=game.no_fans,
            neutral_site=game.neutral_site,
        )

    # -- update ------------------------------------------------------------

    def observe(self, game: Game, prediction: GamePrediction) -> None:
        """Apply a final result. Ignores anything not yet decided."""
        if not game.is_final or game.home_score is None or game.away_score is None:
            return

        home_won = game.home_score > game.away_score

        # A regulation win is worth a full point; overtime and the shootout are
        # close enough to coin flips that they get partial credit.
        if game.went_past_regulation:
            s_home = self.params.ot_credit if home_won else 1.0 - self.params.ot_credit
        else:
            s_home = 1.0 if home_won else 0.0

        expected_home = prediction.home_win_prob
        goal_diff = game.home_score - game.away_score

        # Winner's perspective on the pregame difference, for the MOV damping.
        raw_diff = prediction.home_elo_pre + prediction.hfa_applied - prediction.away_elo_pre
        winner_diff = raw_diff if home_won else -raw_diff

        mult = mov_multiplier(goal_diff, winner_diff, self.params.mov_const)
        delta = self.params.k * mult * (s_home - expected_home)

        home_key = rating_key(game.home_id)
        away_key = rating_key(game.away_id)
        self.ratings[home_key] += delta
        self.ratings[away_key] -= delta  # zero-sum

        self._last_played[home_key] = game.date_et
        self._last_played[away_key] = game.date_et

    # -- driver ------------------------------------------------------------

    def run(self, games: Iterable[Game]) -> Iterator[GamePrediction]:
        """Walk games in order, yielding each prediction before applying it.

        Games must already be sorted by date. Sorting here would hide a caller
        bug that silently trains on the future.
        """
        for game in games:
            self._roll_season(game.season)
            prediction = self.predict(game)
            yield prediction
            self.observe(game, prediction)
