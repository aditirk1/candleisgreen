"""Drift monitoring (spec decision Q6): each signal's platform record against its forecast
distribution. An alert demotes one tier and opens a re-evaluation case."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from ..composite.monitoring import deterioration_test
from ..core.config import AppConfig
from .registry import ResearchRegistry


def check(registry: ResearchRegistry, signal_id: str, daily_net: np.ndarray, mu_hat: float, mu_var: float,
          horizon: int, cfg: AppConfig, now: datetime) -> dict:
    res = deterioration_test(daily_net, mu_hat, mu_var, horizon, cfg.composite.monitoring)
    out = {"signal_id": signal_id, "status": res.status, "probability": res.probability}
    if res.status == "alert":
        tier, status, evidence = registry.tier(signal_id)
        if tier > 1:
            registry.set_tier(signal_id, tier - 1, "SUSPENDED", {**evidence, "drift_probability": res.probability}, now)
        out["case_id"] = registry.open_reevaluation(signal_id, f"drift:{now.date().isoformat()}", now)
        out["tier_after"] = registry.tier(signal_id)[0]
    return out
