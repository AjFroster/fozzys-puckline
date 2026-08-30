"""Team-id continuity. Getting this wrong silently resets a club's rating."""

from __future__ import annotations

import pytest

from fozzys_puckline import identity
from fozzys_puckline.identity import is_expansion, rating_key


def test_ordinary_team_is_its_own_key() -> None:
    assert rating_key(10) == 10


def test_utah_chain_resolves_back_to_arizona() -> None:
    """68 -> 59 -> 53. The API links 59 and 68 by franchise, but nothing links
    either to Arizona, so all three must resolve to one rating history."""
    assert rating_key(68) == 53
    assert rating_key(59) == 53
    assert rating_key(53) == 53


def test_expansion_clubs_are_not_continuations() -> None:
    assert is_expansion(54)  # Vegas
    assert is_expansion(55)  # Seattle
    assert not is_expansion(68)  # Utah continues Arizona
    assert not is_expansion(10)


def test_cycle_in_the_map_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "TEAM_CONTINUITY", {1: 2, 2: 1})
    with pytest.raises(ValueError, match="cycle"):
        rating_key(1)
