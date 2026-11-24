"""Champion and challenger (spec Phase 5). A challenger is compared with the champion out of
sample. The comparison can only recommend: the switch needs Aditi's approval."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from ..core.config import AppConfig
from .criteria import forecast_beats_baseline
from .registry import ResearchRegistry


def compare(registry: ResearchRegistry, claim_id: str, champion: str, challenger: str, y: np.ndarray,
            f_champion: np.ndarray, f_challenger: np.ndarray, nested: bool, horizon: int, cfg: AppConfig,
            now: datetime, data_labels: tuple[str, ...] = ()) -> dict:
    plan = {"study": "forecast", "champion": champion, "challenger": challenger, "nested": nested,
            "rule": "challenger beats champion out of sample and holds in 2 of 3 subperiods", "data_labels": list(data_labels)}
    eid = registry.preregister(claim_id, "forecast", plan, now)
    result = forecast_beats_baseline(y, f_champion, f_challenger, horizon, nested, cfg.research.criteria)
    evidence_ok = result["passed"] and not ({"SYNTHETIC", "SURVIVORSHIP-BIASED"} & set(data_labels))
    result["recommendation"] = ("propose the challenger for Aditi's approval" if evidence_ok
                                else "keep the champion")
    result["data_labels"] = list(data_labels)
    registry.record_variant(eid, {"challenger": challenger}, result, now)
    registry.complete(eid, plan, bool(result["passed"]), result, now)
    return {"experiment_id": eid, **result}
