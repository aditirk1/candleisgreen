"""Spec v3.2 Q6: infrastructure failures and strategy deterioration are separate.

Infrastructure: missing critical data, invalid prices or a failed risk check pause the
affected trading at once. No statistics are involved.

Strategy: realized out-of-sample returns are compared with the forecast distribution,
which includes both the uncertainty of the edge estimate and the sampling noise of a
finite window. A short window therefore needs a larger shortfall before it alerts. The
alert level and window are provisional and a strategy may declare its own.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..core.config import MonitoringConfig
from .stats import newey_west_se, normal_cdf, nw_lag


@dataclass(frozen=True)
class InfrastructureStatus:
    paused: bool
    reasons: tuple[str, ...]


def infrastructure_check(critical_data_present: Optional[bool], prices_valid: Optional[bool],
                         risk_check_passed: Optional[bool]) -> InfrastructureStatus:
    """Any failure or unknown pauses the affected trading immediately."""
    reasons = []
    for name, ok in (("critical data", critical_data_present), ("price validity", prices_valid),
                     ("risk check", risk_check_passed)):
        if ok is None:
            reasons.append(f"{name} unknown")
        elif not ok:
            reasons.append(f"{name} failed")
    return InfrastructureStatus(bool(reasons), tuple(reasons))


@dataclass(frozen=True)
class DeteriorationResult:
    status: str  # ok, alert, insufficient_data
    probability: Optional[float]  # chance of a result this bad if the forecast were right
    realized_mean_annual: Optional[float]
    predictive_sd_annual: Optional[float]
    observations: int


def deterioration_test(daily_net: np.ndarray, mu_hat_annual: float, mu_var_annual: float, horizon_days: int,
                       cfg: MonitoringConfig, max_lag: int = 63, days_per_year: int = 252,
                       window_days: Optional[int] = None, alert_probability: Optional[float] = None) -> DeteriorationResult:
    window = window_days or cfg.review_window_days
    level = alert_probability or cfg.alert_probability
    x = np.asarray(daily_net, dtype=float)[-window:]
    n = int(x.size)
    if n < cfg.min_observation_days:
        return DeteriorationResult("insufficient_data", None, None, None, n)
    realized = float(x.mean()) * days_per_year
    sampling_se = newey_west_se(x, nw_lag(horizon_days, n, max_lag)) * days_per_year
    sd = math.sqrt(max(mu_var_annual, 0.0) + sampling_se**2)
    prob = normal_cdf((realized - mu_hat_annual) / sd) if sd > 0 else 0.0
    return DeteriorationResult("alert" if prob < level else "ok", prob, realized, sd, n)
