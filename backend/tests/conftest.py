from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Any:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def bulk_payload() -> dict[str, Any]:
    """Three real 2015-16 games: one REG, one OT, one SO."""
    return _load("bulk_game.json")


@pytest.fixture
def score_payload() -> dict[str, Any]:
    """Two real games from the api-web score endpoint."""
    return _load("score_day.json")


@pytest.fixture
def teams_payload() -> dict[str, Any]:
    return _load("teams.json")
