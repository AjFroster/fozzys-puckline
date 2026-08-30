"""Team goal rates, and the walk-forward totals engine.

Rates are estimated on *regulation* goals. Using final scores instead would fold
the overtime and shootout goal into every team's attack rate and inflate every
total the model publishes.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field

from fozzys_puckline.goals import TotalDistribution, final_total_distribution
from fozzys_puckline.identity import rating_key
from fozzys_puckline.schemas import Game

DEFAULT_LINES: tuple[float, ...] = (5.5, 6.5)
"""The two lines books actually hang on NHL totals."""


@dataclass(frozen=True, slots=True)
class TotalsParams:
    """Tunables for the goal-rate model."""

    half_life: float = 20.0
    """Games until a result carries half its original weight."""

    prior_games: float = 30.0
    """Strength of the shrink toward league average, in games. Keeps an
    early-season 3-0-0 team from being modelled as a juggernaut."""

    carryover: float = 0.60
    """Between seasons, rate multipliers regress this far toward 1.0."""

    dispersion: float = 1.15
    """Conway-Maxwell-Poisson shape. Above 1.0 is under-dispersed, which is what
    NHL totals are: variance 5.29 against mean 6.00 over the backfill."""

    tie_intercept: float = 0.93
    tie_slope: float = -0.088
    """Score-effect correction to P(tie | regulation total); see goals.py."""

    league_half_life: float = 2000.0
    """Half-life for the league scoring rate, in team-games (~1000 games).

    Much longer than a team's own half-life on purpose: league scoring drifts
    across eras rather than week to week, and it rose from 5.41 goals per game
    in 2015-16 to 6.35 in 2022-23.

    Pinned rather than fitted. Sweeping it from 300 to 4000 team-games moves
    validation log likelihood by under 1e-4 and the over/under hit rate not at
    all, so there is nothing here for a search to find.
    """

    league_goals: float = 2.886
    """Regulation goals per team per game. Seeds the model before enough games
    exist to measure it, then gets updated from the data as the season runs."""

    home_share: float = 0.5209
    """Home team's share of regulation goals. Measured over the backfill:
    3.0065 home against 2.7648 away."""

    def replace(self, **changes: float) -> TotalsParams:
        return TotalsParams(**{**asdict(self), **changes})


FITTED_FIELDS = ("half_life", "prior_games", "carryover")
"""Only the rate model is searched.

`dispersion`, `home_share`, `league_goals`, and the two tie parameters are
measured directly from the validation seasons by `calibrate`, not fitted. Each
is pinned down far more precisely by its own statistic — the variance-to-mean
ratio, the goal split, the conditional tie curve — than a likelihood search can
manage while trading it off against overall distribution shape.

That distinction is not academic. When `tie_intercept` was inside the sweep it
moved to 0.5 and made the published over/under measurably worse, because the
likelihood was happy to pay for shape fit with a quantity we can measure.
"""


@dataclass(frozen=True, slots=True)
class TotalsPrediction:
    game_id: int
    season: int
    game_type: int
    date_et: dt.date
    exp_goals_home: float
    exp_goals_away: float
    exp_total: float
    fair_total_line: float
    fair_line_p_over: float
    tie_probability: float
    lines: tuple[tuple[float, float], ...]
    """(line, p_over) pairs."""
    pmf: tuple[float, ...]
    """Full final-total distribution, so likelihood needs no recomputation."""
    actual_total: int | None

    @property
    def scored(self) -> bool:
        return self.actual_total is not None

    def p_over(self, line: float) -> float | None:
        for candidate, prob in self.lines:
            if candidate == line:
                return prob
        return None


@dataclass(slots=True)
class _TeamRates:
    """Exponentially weighted regulation goals for and against."""

    goals_for: float = 0.0
    goals_against: float = 0.0
    weight: float = 0.0

    def decay(self, factor: float) -> None:
        self.goals_for *= factor
        self.goals_against *= factor
        self.weight *= factor

    def add(self, scored: int, conceded: int, factor: float) -> None:
        """Age this team's history by one of ITS games, then record the result.

        Decaying here rather than on every league game is the whole point: a
        team plays 82 of the season's 1,312 games, so ageing every team on every
        game applies the half-life about sixteen times too fast and collapses
        every multiplier onto the league prior.
        """
        self.decay(factor)
        self.goals_for += scored
        self.goals_against += conceded
        self.weight += 1.0


@dataclass(slots=True)
class TotalsEngine:
    """Walk-forward goal-rate state.

    Mirrors EloEngine: `run` yields each prediction before the result that
    would inform it is applied.
    """

    params: TotalsParams = field(default_factory=TotalsParams)
    rates: dict[int, _TeamRates] = field(default_factory=dict)
    _season: int | None = field(default=None, repr=False)
    _league_for: float = field(default=0.0, repr=False)
    _league_games: float = field(default=0.0, repr=False)

    @property
    def _decay(self) -> float:
        """Per-team-game decay factor."""
        return float(0.5 ** (1.0 / self.params.half_life))

    @property
    def _league_decay(self) -> float:
        """Per-team-game decay factor for the league aggregate."""
        return float(0.5 ** (1.0 / self.params.league_half_life))

    def _team(self, team_id: int) -> _TeamRates:
        return self.rates.setdefault(rating_key(team_id), _TeamRates())

    def league_goals(self) -> float:
        """Regulation goals per team per game, blended toward the seed value."""
        prior = self.params.prior_games
        seeded = self.params.league_goals * prior
        return (self._league_for + seeded) / (self._league_games + prior)

    def _multipliers(self, team_id: int, league: float) -> tuple[float, float]:
        """(attack, defense) multipliers, shrunk toward league average.

        Both centre on 1.0, so a team with no history predicts exactly league
        average rather than nothing.
        """
        rates = self._team(team_id)
        prior = self.params.prior_games
        denominator = (rates.weight + prior) * league
        if denominator <= 0:
            return 1.0, 1.0
        attack = (rates.goals_for + prior * league) / denominator
        defense = (rates.goals_against + prior * league) / denominator
        return attack, defense

    def _roll_season(self, season: int) -> None:
        if self._season is None:
            self._season = season
            return
        if season == self._season:
            return
        # Regress every team's accumulated weight, which pulls its multipliers
        # back toward 1.0 without discarding what was learned.
        factor = self.params.carryover
        for rates in self.rates.values():
            rates.decay(factor)
        self._season = season

    def predict(self, game: Game) -> TotalsPrediction:
        league = self.league_goals()
        attack_home, defense_home = self._multipliers(game.home_id, league)
        attack_away, defense_away = self._multipliers(game.away_id, league)

        share = self.params.home_share
        lam_home = 2.0 * league * share * attack_home * defense_away
        lam_away = 2.0 * league * (1.0 - share) * attack_away * defense_home

        distribution = self._distribution(lam_home, lam_away)
        actual = game.total_goals if game.is_final else None

        return TotalsPrediction(
            game_id=game.game_id,
            season=game.season,
            game_type=game.game_type,
            date_et=game.date_et,
            exp_goals_home=lam_home,
            exp_goals_away=lam_away,
            exp_total=distribution.expected,
            fair_total_line=distribution.fair_line(),
            fair_line_p_over=distribution.fair_line_p_over(),
            tie_probability=distribution.tie_probability,
            lines=tuple((line, distribution.p_over(line)) for line in DEFAULT_LINES),
            pmf=distribution.pmf,
            actual_total=actual,
        )

    def _distribution(self, lam_home: float, lam_away: float) -> TotalDistribution:
        return final_total_distribution(
            lam_home,
            lam_away,
            tie_intercept=self.params.tie_intercept,
            tie_slope=self.params.tie_slope,
            dispersion=self.params.dispersion,
        )

    def observe(self, game: Game) -> None:
        """Fold a final result into both teams' rates and the league average."""
        regulation = game.regulation_scores
        if regulation is None:
            return
        home_goals, away_goals = regulation

        decay = self._decay
        self._team(game.home_id).add(home_goals, away_goals, decay)
        self._team(game.away_id).add(away_goals, home_goals, decay)

        # The league aggregate takes two team-games from this result.
        league_decay = self._league_decay**2
        self._league_for = self._league_for * league_decay + home_goals + away_goals
        self._league_games = self._league_games * league_decay + 2.0

    def run(self, games: Iterable[Game]) -> Iterator[TotalsPrediction]:
        for game in games:
            self._roll_season(game.season)
            yield self.predict(game)
            self.observe(game)


def implied_home_win_probability(prediction: TotalsPrediction) -> float:
    """Deliberately not provided — see the note below.

    The plan called for cross-checking the Elo win probability against the one
    implied by the goal model. That check is not shipped, because independent
    Poisson misprices the regulation margin by up to 11 points (30.8% predicted
    one-goal games against 19.6% observed). A disagreement flag built on it
    would fire constantly on the goal model's own defect rather than on any real
    disagreement, which is worse than having no check at all.
    """
    raise NotImplementedError(
        "independent Poisson misprices the margin; use Elo for win probability"
    )


EPSILON = 1e-12


def mean_log_likelihood(predictions: Iterable[TotalsPrediction]) -> float:
    """Mean log likelihood of the observed totals. Higher is better.

    This is the objective the sweep optimises. Hit rate at the fair line is a
    calibration check, not a fitting target — a model can sit at exactly 50%
    while being uselessly vague about every individual game.
    """
    total = 0.0
    count = 0
    for prediction in predictions:
        actual = prediction.actual_total
        if actual is None:
            continue
        p = prediction.pmf[actual] if actual < len(prediction.pmf) else 0.0
        total += math.log(max(p, EPSILON))
        count += 1
    return total / count if count else float("nan")
