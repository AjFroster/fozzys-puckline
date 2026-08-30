"""Probability to odds.

Everything published here is **fair** — no vig, no margin, no book's price. The
site labels it that way, and nothing in this project quotes a sportsbook line.
"""

from __future__ import annotations

MIN_PROBABILITY = 1e-6


def american_odds(probability: float) -> int:
    """Fair American odds for a probability.

    Favourites are negative (stake needed to win 100), underdogs positive
    (profit on a 100 stake). A coin flip is -100 by convention.
    """
    p = min(max(probability, MIN_PROBABILITY), 1.0 - MIN_PROBABILITY)
    if p >= 0.5:
        return -round(100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def decimal_odds(probability: float) -> float:
    """Fair decimal odds: total return per unit staked, including the stake."""
    p = min(max(probability, MIN_PROBABILITY), 1.0 - MIN_PROBABILITY)
    return round(1.0 / p, 3)


def implied_probability(american: int) -> float:
    """Inverse of `american_odds`, for checking a quoted price."""
    if american < 0:
        return -american / (-american + 100.0)
    return 100.0 / (american + 100.0)
