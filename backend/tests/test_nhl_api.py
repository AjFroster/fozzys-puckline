"""The client's job is to be boring under a flaky, undocumented API."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx

from fozzys_puckline import config
from fozzys_puckline.sources.nhl_api import (
    NhlApi,
    NhlApiError,
    RequestBudgetExceeded,
    team_tricodes,
)


def _api(**kwargs: object) -> NhlApi:
    # snapshot=False keeps tests off the filesystem; throttle=0 keeps them fast.
    return NhlApi(snapshot=False, throttle=0.0, **kwargs)  # type: ignore[arg-type]


@respx.mock
def test_retries_a_server_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    route = respx.get(f"{config.WEB_API}/score/2026-03-01").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"games": []}),
        ]
    )

    with _api() as api:
        payload = api.score(dt.date(2026, 3, 1))

    assert payload == {"games": []}
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    respx.get(f"{config.WEB_API}/score/2026-03-01").mock(return_value=httpx.Response(500))

    with _api(max_retries=3) as api, pytest.raises(NhlApiError):
        api.score(dt.date(2026, 3, 1))


@respx.mock
def test_does_not_retry_a_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404 is an answer, not a hiccup — retrying it just wastes their quota."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    route = respx.get(f"{config.WEB_API}/score/2026-03-01").mock(return_value=httpx.Response(404))

    with _api() as api, pytest.raises(NhlApiError):
        api.score(dt.date(2026, 3, 1))

    assert route.call_count == 1


@respx.mock
def test_request_budget_stops_a_runaway_loop() -> None:
    respx.get(f"{config.STATS_API}/team").mock(return_value=httpx.Response(200, json={"data": []}))

    with _api(budget=1) as api:
        api.teams()
        with pytest.raises(RequestBudgetExceeded):
            api.teams()


@respx.mock
def test_season_games_requests_the_whole_season() -> None:
    route = respx.get(f"{config.STATS_API}/game").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0})
    )

    with _api() as api:
        api.season_games(20152016, 2)

    request = route.calls[0].request
    assert request.url.params["limit"] == "-1"
    assert request.url.params["cayenneExp"] == "season=20152016 and gameType=2"


def test_team_tricodes_builds_the_lookup() -> None:
    payload = {"data": [{"id": 10, "triCode": "TOR"}, {"id": 8, "triCode": "MTL"}]}
    assert team_tricodes(payload) == {10: "TOR", 8: "MTL"}
