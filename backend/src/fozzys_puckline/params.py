"""Model parameters.

Five of these are fitted; the rest are held fixed on purpose. The backfill
window is ~14,000 regular-season games, which is small enough that a wide search
finds noise rather than signal, so the sweep is capped at five free parameters
and everything else is pinned to a value with a stated reason.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

PARAMS_PATH = Path(__file__).resolve().parents[2] / "params.json"

BASE_RATING = 1500.0


@dataclass(frozen=True, slots=True)
class EloParams:
    """Tunables for the rating engine."""

    # --- fitted ------------------------------------------------------------
    k: float = 6.0
    """Update size. 82 games is many updates; low K keeps a high-variance sport stable."""

    hfa: float = 35.0
    """Home ice, in Elo points. Fitted, never hardcoded — it has drifted for a decade."""

    ot_credit: float = 0.65
    """Credit for an OT or shootout win. A 3-on-3 or a shootout is near a coin flip,
    so awarding a full win teaches the model something false."""

    carryover: float = 0.70
    """Between seasons, R = carryover * R + (1 - carryover) * league_mean."""

    diff_scale: float = 1.0
    """Multiplier on the rating difference before the logistic, equivalent to
    changing Elo's 400 divisor. Corrects systematic under- or over-confidence
    that the rating scale itself cannot express. Fitting lands it at 1.0, which
    is the evidence that the rating scale needs no correction."""

    # --- held fixed --------------------------------------------------------
    mov_const: float = 2.05
    """Margin-of-victory damping. Pinned, not fitted: across the validation set
    it is flat to the fifth decimal from 3.0 upward, while holdout log loss
    degrades monotonically as it rises (0.68864 at 2.05, 0.69027 at 100). A
    sweep given this axis spends it chasing noise off the end of the grid."""

    b2b_penalty: float = 25.0
    """Pregame only. A team on the second of back-to-back nights is temporarily
    worse, not permanently worse, so this never touches the stored rating."""

    expansion_init: float = 1380.0
    """Vegas and Seattle notwithstanding, new clubs do not start league-average."""

    no_fans_hfa_factor: float = 0.45
    """Empty buildings roughly halve home ice. Measured over this window: home
    teams won 53.96% of 13,426 games with a crowd against 52.50% of 1,082
    without. Fixed from that measurement rather than fitted, to keep the free
    parameter count at five."""

    def replace(self, **changes: float) -> EloParams:
        return EloParams(**{**asdict(self), **changes})

    def to_json(self, path: Path | None = None) -> Path:
        target = path or PARAMS_PATH
        target.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return target

    @classmethod
    def from_json(cls, path: Path | None = None) -> EloParams:
        target = path or PARAMS_PATH
        if not target.exists():
            return cls()
        return cls(**json.loads(target.read_text(encoding="utf-8")))


# The parameters the sweep is allowed to touch.
FITTED_FIELDS = ("k", "hfa", "ot_credit", "carryover", "diff_scale")
