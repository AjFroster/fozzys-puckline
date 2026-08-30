"""The seam between Python and the site.

Two things are checked here: that the published files parse back into the models
that produced them, and that the hand-written TypeScript mirror has not drifted.
Drift is the failure mode that matters — a renamed field surfaces on the site as
`undefined` rather than as an error, so it needs to fail in CI instead.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import get_type_hints

import pytest

from fozzys_puckline import contracts, odds
from fozzys_puckline.params import ModelParams
from fozzys_puckline.publish import build_slate_game, model_version, publish, run_models
from fozzys_puckline.schemas import Game

CONTRACT_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "types" / "contract.ts"

MODELS = [
    contracts.TeamSide,
    contracts.TotalLine,
    contracts.Prediction,
    contracts.GameResult,
    contracts.SlateGame,
    contracts.Slate,
    contracts.TeamRating,
    contracts.Ratings,
    contracts.RatingPoint,
    contracts.RatingHistory,
    contracts.Team,
    contracts.Teams,
    contracts.CalibrationBin,
    contracts.WindowMetrics,
    contracts.TotalsMetrics,
    contracts.SeasonMetrics,
    contracts.Metrics,
    contracts.IndexEntry,
    contracts.Index,
]


def _ts_source() -> str:
    return CONTRACT_TS.read_text(encoding="utf-8")


def _ts_interface(name: str, source: str) -> str | None:
    match = re.search(rf"export interface {name}\b[^{{]*{{(.*?)\n}}", source, re.S)
    return match.group(1) if match else None


# -- TypeScript parity ------------------------------------------------------


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_model_has_a_typescript_interface(model: type) -> None:
    assert _ts_interface(model.__name__, _ts_source()) is not None


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_python_field_appears_in_typescript(model: type) -> None:
    source = _ts_source()
    body = _ts_interface(model.__name__, source)
    assert body is not None

    # Word boundary matters: "interface Slate" also prefix-matches
    # "interface SlateGame", which does not extend Document.
    declaration = re.search(rf"export interface {model.__name__}\b[^{{]*", source)
    assert declaration is not None
    inherited = "extends Document" in declaration.group(0)
    document_fields = {"schema", "generated_at", "model_version"}

    for name in get_type_hints(model):
        field = model.model_fields[name]  # type: ignore[attr-defined]
        published = field.serialization_alias or name
        if inherited and published in document_fields:
            continue
        assert re.search(rf"\b{re.escape(published)}\??:", body), (
            f"{model.__name__}.{published} is missing from contract.ts"
        )


def test_the_document_stamp_is_serialised_as_schema() -> None:
    """`schema` shadows a pydantic builtin in Python but is the wire name."""
    payload = contracts.Index(
        generated_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        model_version="test",
        latest_date=None,
        dates=[],
    ).model_dump(mode="json", by_alias=True)
    assert payload["schema"] == contracts.SCHEMA_VERSION
    assert "schema_version" not in payload


# -- odds -------------------------------------------------------------------


def test_a_favourite_prices_negative_and_an_underdog_positive() -> None:
    assert odds.american_odds(0.75) < 0
    assert odds.american_odds(0.25) > 0


def test_a_coin_flip_is_minus_one_hundred() -> None:
    assert odds.american_odds(0.5) == -100


def test_american_odds_round_trip() -> None:
    for p in (0.2, 0.35, 0.5, 0.62, 0.8):
        assert odds.implied_probability(odds.american_odds(p)) == pytest.approx(p, abs=0.005)


def test_decimal_odds_are_the_reciprocal() -> None:
    assert odds.decimal_odds(0.25) == pytest.approx(4.0)


def test_odds_do_not_blow_up_at_the_extremes() -> None:
    for p in (0.0, 1.0):
        assert isinstance(odds.american_odds(p), int)
        assert odds.decimal_odds(p) > 0


# -- published documents ----------------------------------------------------


def _game(gid: int, day: int, *, final: bool = True) -> Game:
    return Game(
        game_id=gid,
        season=20232024,
        game_type=2,
        date_et=dt.date(2024, 1, day),
        start_utc=dt.datetime(2024, 1, day, 23, tzinfo=dt.UTC),
        home_id=10,
        away_id=8,
        home_abbrev="TOR",
        away_abbrev="MTL",
        home_score=3 if final else None,
        away_score=2 if final else None,
        last_period="REG" if final else None,
        state="FINAL" if final else "FUT",
        venue="Scotiabank Arena",
    )


def test_publish_writes_every_expected_file(tmp_path: Path) -> None:
    games = [_game(i, i + 1) for i in range(12)] + [_game(99, 20, final=False)]

    report = publish(
        games,
        ModelParams(),
        today=dt.date(2024, 1, 15),
        holdout=20232024,
        out_dir=tmp_path,
    )

    names = {p.relative_to(tmp_path).as_posix() for p in report.files}
    assert "latest.json" in names
    assert "index.json" in names
    assert "teams.json" in names
    assert "metrics.json" in names
    assert "ratings/current.json" in names
    assert "ratings/history.json" in names
    assert any(n.startswith("slate/") for n in names)


def test_published_files_parse_back_into_their_models(tmp_path: Path) -> None:
    games = [_game(i, i + 1) for i in range(12)]
    publish(games, ModelParams(), today=dt.date(2024, 1, 15), holdout=20232024, out_dir=tmp_path)

    for name, model in (
        ("latest.json", contracts.Slate),
        ("index.json", contracts.Index),
        ("teams.json", contracts.Teams),
        ("ratings/current.json", contracts.Ratings),
        ("ratings/history.json", contracts.RatingHistory),
    ):
        payload = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        payload["schema_version"] = payload.pop("schema")
        model.model_validate(payload)


def test_latest_points_at_the_next_game_day_when_nobody_plays_today(tmp_path: Path) -> None:
    """Without the fallback the homepage is blank all offseason."""
    games = [_game(1, 5), _game(2, 25, final=False)]

    report = publish(
        games, ModelParams(), today=dt.date(2024, 1, 15), holdout=20232024, out_dir=tmp_path
    )

    assert report.latest == dt.date(2024, 1, 25)


def test_win_probabilities_are_complementary_and_odds_agree() -> None:
    game = _game(1, 5)
    run = run_models([game], ModelParams())
    slate = build_slate_game(game, run.elo[1], run.totals[1])

    prediction = slate.prediction
    assert prediction.home_win_prob + prediction.away_win_prob == pytest.approx(1.0, abs=1e-4)
    # Fair prices, so exactly one side is the favourite.
    assert (prediction.home_ml_fair < 0) != (prediction.away_ml_fair < 0)


def test_a_result_is_present_exactly_when_the_game_is_final() -> None:
    played, scheduled = _game(1, 5), _game(2, 6, final=False)
    run = run_models([played, scheduled], ModelParams())

    assert build_slate_game(played, run.elo[1], run.totals[1]).result is not None
    assert build_slate_game(scheduled, run.elo[2], run.totals[2]).result is None


def test_model_version_tracks_the_parameters() -> None:
    base = ModelParams()
    moved = ModelParams(elo=base.elo.replace(k=99.0), totals=base.totals)
    assert model_version(base) != model_version(moved)
    assert model_version(base) == model_version(ModelParams())


# -- idempotency ------------------------------------------------------------


def test_republishing_unchanged_data_writes_nothing(tmp_path: Path) -> None:
    """The nightly job commits whatever publishing touches.

    Every document carries a wall-clock stamp, so a naive write dirties all 43
    files every run — committing nightly whether or not anything happened and
    burning a Cloudflare Pages build each time against a 500-a-month quota.
    """
    games = [_game(i, i + 1) for i in range(8)]
    args = {"today": dt.date(2024, 1, 15), "holdout": 20232024, "out_dir": tmp_path}

    first = publish(games, ModelParams(), **args)  # type: ignore[arg-type]
    before = {p: p.read_bytes() for p in first.files}

    second = publish(games, ModelParams(), **args)  # type: ignore[arg-type]

    assert first.changed, "the first run should write everything"
    assert second.changed == [], "the second run should write nothing"
    assert all(p.read_bytes() == before[p] for p in second.files)


def test_real_changes_still_get_written(tmp_path: Path) -> None:
    """Skipping unchanged files must not skip changed ones."""
    args = {"today": dt.date(2024, 1, 15), "holdout": 20232024, "out_dir": tmp_path}
    publish([_game(i, i + 1) for i in range(8)], ModelParams(), **args)  # type: ignore[arg-type]

    with_result = [_game(i, i + 1) for i in range(9)]
    second = publish(with_result, ModelParams(), **args)  # type: ignore[arg-type]

    assert second.changed, "a new game should produce a write"
