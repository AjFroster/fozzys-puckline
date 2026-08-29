"""Thin typed client for the NHL's public APIs.

Both APIs here are undocumented and unofficial, so this module assumes they will
change shape without notice. Two structural defences:

  1. Every response is snapshotted to data/raw/ before anything parses it.
     Parsing is a separate pass over local files, so a schema change costs a
     parser fix and a replay, not a re-crawl and not a lost day of history.
  2. Requests are throttled, retried with jittered backoff, and hard-capped per
     process.
"""

from __future__ import annotations

import datetime as dt
import random
import time
from typing import Any

import httpx

from fozzys_puckline import config
from fozzys_puckline.store import write_snapshot

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

JsonDict = dict[str, Any]


class NhlApiError(RuntimeError):
    """Raised when the API cannot be reached after exhausting retries."""


class RequestBudgetExceeded(NhlApiError):
    """Raised when a single process tries to exceed MAX_REQUESTS_PER_RUN."""


class NhlApi:
    """Fetches NHL JSON, snapshots it, and hands back the parsed payload."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        snapshot: bool = True,
        throttle: float = config.THROTTLE_SECONDS,
        max_retries: int = config.MAX_RETRIES,
        budget: int = config.MAX_REQUESTS_PER_RUN,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._snapshot = snapshot
        self._throttle = throttle
        self._max_retries = max_retries
        self._budget = budget
        self._requests_made = 0
        self._last_request_at = 0.0

    # -- plumbing ----------------------------------------------------------

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)

    def _get(self, url: str, params: JsonDict | None = None) -> JsonDict:
        if self._requests_made >= self._budget:
            raise RequestBudgetExceeded(
                f"request budget of {self._budget} exhausted; refusing to continue"
            )

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            self._wait_turn()
            self._requests_made += 1
            self._last_request_at = time.monotonic()
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:  # timeouts, connection resets
                last_error = exc
            else:
                if response.status_code == 200:
                    payload: JsonDict = response.json()
                    return payload
                if response.status_code not in RETRY_STATUS:
                    raise NhlApiError(f"{response.status_code} from {response.url}")
                last_error = NhlApiError(f"{response.status_code} from {response.url}")

            # Exponential backoff with full jitter, so parallel jobs desynchronize.
            delay = (config.BACKOFF_BASE**attempt) * (0.5 + random.random())
            time.sleep(delay)

        raise NhlApiError(f"giving up on {url} after {self._max_retries} attempts") from last_error

    def _fetch(self, url: str, snapshot_key: str, params: JsonDict | None = None) -> JsonDict:
        payload = self._get(url, params)
        if self._snapshot:
            write_snapshot(snapshot_key, payload)
        return payload

    # -- endpoints ---------------------------------------------------------

    def teams(self) -> JsonDict:
        """Team reference data, including historical franchises. id -> triCode."""
        return self._fetch(f"{config.STATS_API}/team", "reference/team")

    def season_games(self, season: int, game_type: int) -> JsonDict:
        """Every game in one season/type. `limit=-1` returns the full set."""
        return self._fetch(
            f"{config.STATS_API}/game",
            f"bulk/game_{season}_{game_type}",
            params={
                "cayenneExp": f"season={season} and gameType={game_type}",
                "limit": -1,
            },
        )

    def score(self, date_et: dt.date) -> JsonDict:
        """One league day: final scores, shots, and OT/SO outcome."""
        iso = date_et.isoformat()
        return self._fetch(f"{config.WEB_API}/score/{iso}", f"{iso[:4]}/{iso[5:7]}/{iso}/score")

    def schedule(self, date_et: dt.date) -> JsonDict:
        """The game week containing `date_et`."""
        iso = date_et.isoformat()
        return self._fetch(
            f"{config.WEB_API}/schedule/{iso}", f"{iso[:4]}/{iso[5:7]}/{iso}/schedule"
        )

    # -- lifecycle ---------------------------------------------------------

    @property
    def requests_made(self) -> int:
        return self._requests_made

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NhlApi:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def team_tricodes(payload: JsonDict) -> dict[int, str]:
    """team id -> triCode, from a /stats/rest/en/team payload."""
    return {int(row["id"]): str(row["triCode"]) for row in payload.get("data", [])}
