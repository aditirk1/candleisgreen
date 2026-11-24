"""Split and dividend adjustment of raw closes, point in time.

Only actions effective on or before the decision date are applied. An action effective by
then is public by then, so this never uses future information.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence


def adjust_closes(closes: Sequence[tuple[date, float]], actions: Sequence[dict], decision_date: date) -> list[tuple[date, float]]:
    """Total-return adjusted closes, scaled so the latest close is unchanged."""
    if not closes:
        return []
    factors = [1.0] * len(closes)
    days = [d for d, _ in closes]
    for act in actions:
        eff = act["effective_date"]
        if eff is None or eff > decision_date:
            continue
        raw = act["raw"]
        kind = act["action_type"]
        if kind in ("forward_splits", "reverse_splits"):
            ratio = float(raw["new_rate"]) / float(raw["old_rate"])
            mult = 1.0 / ratio
        elif kind == "cash_dividends":
            prior = [c for d, c in closes if d < eff]
            if not prior or prior[-1] <= 0:
                continue
            mult = 1.0 - float(raw["rate"]) / prior[-1]
        else:
            continue
        for i, d in enumerate(days):
            if d < eff:
                factors[i] *= mult
    return [(d, c * f) for (d, c), f in zip(closes, factors)]
