"""The fitting loop's job is to not chase noise."""

from __future__ import annotations

import datetime as dt

from fozzys_puckline import fit as fitmod
from fozzys_puckline.fit import fit
from fozzys_puckline.params import EloParams
from fozzys_puckline.schemas import Game


def _season(season: int, count: int, start: dt.date) -> list[Game]:
    return [
        Game(
            game_id=season * 1000 + i,
            season=season,
            game_type=2,
            date_et=start + dt.timedelta(days=i * 2),
            home_id=10 if i % 2 else 8,
            away_id=8 if i % 2 else 10,
            home_abbrev="TOR" if i % 2 else "MTL",
            away_abbrev="MTL" if i % 2 else "TOR",
            home_score=3 if i % 3 else 1,
            away_score=1 if i % 3 else 3,
            last_period="REG",
            state="FINAL",
        )
        for i in range(count)
    ]


GAMES = _season(20222023, 60, dt.date(2022, 10, 10)) + _season(20232024, 60, dt.date(2023, 10, 10))


def test_fit_returns_params_and_a_score() -> None:
    result = fit(GAMES, [20232024], rounds=1)

    assert isinstance(result.params, EloParams)
    assert result.evaluations > 1
    assert result.log_loss > 0


def test_tolerance_blocks_a_sub_noise_move(monkeypatch: object) -> None:
    """A huge tolerance should leave every fitted parameter untouched."""
    start = EloParams()

    result = fit(GAMES, [20232024], start=start, rounds=2, tolerance=1e9)

    assert result.params == start


def test_a_real_improvement_is_still_accepted() -> None:
    result = fit(GAMES, [20232024], rounds=2, tolerance=0.0)

    assert result.log_loss <= fit(GAMES, [20232024], rounds=1, tolerance=1e9).log_loss


def test_pinned_parameters_are_never_searched() -> None:
    """mov_const is pinned on evidence; the sweep must not touch it."""
    assert "mov_const" not in fitmod.FITTED_FIELDS
    assert "mov_const" not in fitmod.GRID

    result = fit(GAMES, [20232024], rounds=2)

    assert result.params.mov_const == EloParams().mov_const
    assert result.params.b2b_penalty == EloParams().b2b_penalty
