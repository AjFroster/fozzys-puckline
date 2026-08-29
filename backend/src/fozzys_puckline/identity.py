"""Which team ids are the same club.

The NHL reissues team ids for relocations and rebrands, and `franchiseId` does
not always bridge them. Inside the 2015-16 backfill window one club changes id
twice:

    ARI (53, franchise 28)  2015-16 .. 2023-24
    UTA Hockey Club (59, franchise 40)  2024-25 only
    UTA Mammoth (68, franchise 40)  2025-26 onward

53 and 59 sit in *different* franchises, so no field in the API links them. The
Coyotes' franchise was deactivated and Utah was issued a new one, even though
the roster moved across intact.

Ratings model on-ice continuity, not legal identity: the club that took the ice
in Utah in 2024-25 was the Arizona roster, and the 2025-26 rebrand changed
nothing but the name. So all three ids resolve to one rating history. Leaving
this out silently resets Utah to an expansion rating twice — once inside the
2025-26 holdout season, which would quietly corrupt the evaluation.

True expansion clubs are separate: Vegas and Seattle really did start from
nothing and get `expansion_init` instead.
"""

from __future__ import annotations

# successor team id -> the id it continues. Chains resolve to the earliest id.
TEAM_CONTINUITY: dict[int, int] = {
    59: 53,  # Utah Hockey Club continues the Arizona roster
    68: 59,  # Utah Mammoth is a rebrand of Utah Hockey Club
}

# Genuinely new clubs, and the season they debuted.
EXPANSION_DEBUT: dict[int, int] = {
    54: 20172018,  # Vegas Golden Knights
    55: 20212022,  # Seattle Kraken
}


def rating_key(team_id: int) -> int:
    """Resolve a team id to the id its rating history is stored under."""
    seen: set[int] = set()
    current = team_id
    while current in TEAM_CONTINUITY:
        if current in seen:  # pragma: no cover - guards a malformed map
            raise ValueError(f"cycle in TEAM_CONTINUITY at {current}")
        seen.add(current)
        current = TEAM_CONTINUITY[current]
    return current


def is_expansion(team_id: int) -> bool:
    return rating_key(team_id) in EXPANSION_DEBUT
