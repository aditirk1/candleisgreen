"""Spec C.5: which signals may enter the Composite, and the Tier 4 economic test."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..core.config import EligibilityConfig
from .edge import EdgeEstimate
from scipy.stats import norm

from .stats import block_bootstrap_mean_interval, newey_west_se, nw_lag

EVENT_TYPES = ("event", "practitioner")


@dataclass(frozen=True)
class SignalState:
    signal_id: str
    family: str
    signal_type: str  # cross_sectional, time_series, event, practitioner
    horizon_days: int
    tier: int
    oos_days: int
    oos_events: int = 0
    feed_healthy: bool = True
    vol_scale: float = 1.0  # g_s
    data_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    capital: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def economic_test(
    daily_net: np.ndarray,
    daily_cost: np.ndarray,
    cfg: EligibilityConfig,
    rng: np.random.Generator,
    days_per_year: int = 252,
) -> tuple[float, bool]:
    """Tier 4 gate: lower bound of the bootstrap interval of net return at multiplied costs.

    `daily_net` already has costs taken off once. The extra (multiplier - 1) x cost is
    taken off here. Returns (annualized lower bound, passed).
    """
    stressed = np.asarray(daily_net, dtype=float) - (cfg.cost_multiplier - 1.0) * np.asarray(daily_cost, dtype=float)
    lower, _ = block_bootstrap_mean_interval(
        stressed, cfg.bootstrap_block_days, cfg.bootstrap_resamples, cfg.interval_level, rng
    )
    return lower * days_per_year, bool(lower > 0)


def replication_test(daily: np.ndarray, horizon_days: int, max_lag: int, cfg: EligibilityConfig) -> tuple[float, bool]:
    """Tier 3 gate for a published signal: positive and significant on independent data.

    Uses a Newey-West t-statistic with lag min(h_s, max_lag, T/4). Returns (t, passed).
    """
    daily = np.asarray(daily, dtype=float)
    se = newey_west_se(daily, nw_lag(horizon_days, daily.size, max_lag))
    t = float(daily.mean() / se) if se > 0 else 0.0
    return t, bool(t > norm.ppf(1.0 - cfg.replication_significance / 2.0))


def is_eligible(state: SignalState, edge: Optional[EdgeEstimate], cfg: EligibilityConfig) -> EligibilityResult:
    reasons: list[str] = []
    if "SURVIVORSHIP-BIASED" in state.data_labels:
        reasons.append("result is SURVIVORSHIP-BIASED and cannot pass any gate")
    if state.tier < cfg.min_tier:
        reasons.append(f"tier {state.tier} below {cfg.min_tier}")
    if edge is None:
        reasons.append("no edge estimate")
    else:
        if not edge.mu_hat > 0:
            reasons.append("estimated edge is not positive")
        if edge.prob_positive < cfg.min_prob_positive:
            reasons.append(f"probability positive {edge.prob_positive:.2f} below {cfg.min_prob_positive:.2f}")
    if state.signal_type in EVENT_TYPES:
        if state.oos_events < cfg.min_events and state.oos_days < cfg.min_oos_days:
            reasons.append(f"{state.oos_events} events and {state.oos_days} days, need {cfg.min_events} events")
    elif state.oos_days < cfg.min_oos_days:
        reasons.append(f"{state.oos_days} out-of-sample days below {cfg.min_oos_days}")
    if not state.feed_healthy:
        reasons.append("data feed is not healthy")
    eligible = not reasons
    return EligibilityResult(eligible, eligible and state.tier >= cfg.capital_min_tier, tuple(reasons))
