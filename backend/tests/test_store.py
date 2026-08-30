"""Idempotency is the property that makes a duplicate cron firing harmless."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fozzys_puckline import normalize, store
from fozzys_puckline.sources.nhl_api import team_tricodes


def test_snapshot_roundtrips(tmp_path: Path) -> None:
    payload = {"games": [{"id": 1}], "note": "verbatim"}

    path = store.write_snapshot("2026/03/01/score", payload, root=tmp_path)

    assert path.exists()
    assert store.read_snapshot("2026/03/01/score", root=tmp_path) == payload


def test_upsert_twice_is_a_no_op(
    tmp_path: Path, bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    games = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))
    target = tmp_path / "games.parquet"

    first = store.upsert_games(games, path=target)
    second = store.upsert_games(games, path=target)

    assert first.height == len(games)
    assert second.height == len(games)
    assert first.equals(second)


def test_upsert_replaces_a_revised_game(
    tmp_path: Path, bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    games = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))
    target = tmp_path / "games.parquet"
    store.upsert_games(games, path=target)

    corrected = games[0].model_copy(update={"home_score": 9})
    frame = store.upsert_games([corrected], path=target)

    assert frame.height == len(games)
    row = frame.filter(store.pl.col("game_id") == corrected.game_id).to_dicts()[0]
    assert row["home_score"] == 9


def test_frames_roundtrip_through_models(
    tmp_path: Path, bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    games = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))

    restored = store.frame_to_games(store.games_to_frame(games))

    assert restored == games


def test_season_counts_groups_by_season_and_type(
    bulk_payload: dict[str, Any], teams_payload: dict[str, Any]
) -> None:
    games = normalize.from_bulk(bulk_payload, team_tricodes(teams_payload))

    counts = store.season_counts(store.games_to_frame(games)).to_dicts()

    assert counts == [{"season": 20152016, "game_type": 2, "games": 3}]


def test_snapshots_are_byte_identical_across_runs(tmp_path: Path) -> None:
    """gzip writes the current time into its header by default.

    Without pinning it, re-snapshotting identical content produces different
    bytes every run — same length, different hash — so the nightly job would
    commit unchanged files every night and burn a Cloudflare Pages build each
    time against a 500-a-month quota.
    """
    payload = {"games": [{"id": 1}], "note": "verbatim"}

    store.write_snapshot("probe", payload, root=tmp_path)
    first = store.snapshot_path("probe", tmp_path).read_bytes()
    time.sleep(1.1)  # long enough for a gzip mtime to move
    store.write_snapshot("probe", payload, root=tmp_path)

    assert store.snapshot_path("probe", tmp_path).read_bytes() == first


def test_a_changed_snapshot_is_still_written(tmp_path: Path) -> None:
    store.write_snapshot("probe", {"a": 1}, root=tmp_path)
    store.write_snapshot("probe", {"a": 2}, root=tmp_path)

    assert store.read_snapshot("probe", root=tmp_path) == {"a": 2}
