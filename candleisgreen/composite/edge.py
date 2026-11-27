"""Spec C.4: estimate each signal's true edge by precision weighting.

All returns are annual fractions at the 10% research volatility (0.03 means 3% a year).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ..core.config import EdgeConfig
from .stats import normal_cdf


@dataclass(frozen=True)
class Evidence:
    kind: str  # "family_prior", "paper" or "out_of_sample"
    value: float
    variance: float

    def __post_init__(self):
        if not (self.variance > 0 and math.isfinite(self.variance) and math.isfinite(self.value)):
            raise ValueError(f"evidence '{self.kind}' needs a finite value and a positive variance")


@dataclass(frozen=True)
class EdgeEstimate:
    mu_hat: float
    variance: float
    prob_positive: float
    evidence_used: tuple[str, ...]

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def interval(self, z: float = 1.6449) -> tuple[float, float]:
        return self.mu_hat - z * self.std, self.mu_hat + z * self.std


def delta_for(group: str, cfg: EdgeConfig) -> Optional[float]:
    """Publication-bias factor by signal group. None means no paper measurement is used."""
    table = {
        "us_published": cfg.delta_us_published,
        "non_us_published": cfg.delta_non_us_published,
        "other_published": cfg.delta_other_published,
        "platform_discovery": None,
        "practitioner": None,
    }
    if group not in table:
        raise ValueError(f"unknown signal group '{group}'")
    return table[group]


def family_delta(oos_returns: Sequence[float], in_sample_returns: Sequence[float], cfg: EdgeConfig) -> Optional[float]:
    """Median out-of-sample to in-sample ratio, once a family has enough signals."""
    pairs = [(o, i) for o, i in zip(oos_returns, in_sample_returns) if i > 0]
    if len(pairs) < cfg.delta_replace_min_signals:
        return None
    return float(np.median([o / i for o, i in pairs]))


def paper_evidence(r_paper: float, se_paper: float, delta: float, modeled_cost: float, cfg: EdgeConfig) -> Evidence:
    """delta x R_paper minus modeled cost. Variance (delta x SE)^2 + omega^2, omega = factor x delta x R."""
    omega = cfg.omega_factor * delta * r_paper
    return Evidence("paper", delta * r_paper - modeled_cost, (delta * se_paper) ** 2 + omega**2)


def oos_evidence(mean: float, se: float) -> Evidence:
    return Evidence("out_of_sample", mean, se**2)


def academic_evidence(mean: float, se: float, modeled_cost: float, cfg: EdgeConfig) -> Evidence:
    """Out-of-sample academic portfolio returns (after the selection cutoff).

    They support the hypothesis but are not the tradable version, so they carry extra
    variance (implementation_gap_factor x mean)^2 and never certify an implementation.
    """
    gap = cfg.implementation_gap_factor * mean
    return Evidence("academic_oos", mean - modeled_cost, se**2 + gap**2)


def family_prior(other_means: Sequence[float], other_ses: Sequence[float], cfg: EdgeConfig) -> Evidence:
    """Prior from the OTHER signals in the family (leave-one-out is the caller's job)."""
    means = np.asarray(other_means, dtype=float)
    ses = np.asarray(other_ses, dtype=float)
    if means.size < cfg.family_min_signals_for_prior:
        return Evidence("family_prior", 0.0, cfg.cold_start_tau_annual**2)
    precision = 1.0 / ses**2
    m_k = float((means * precision).sum() / precision.sum())
    tau2 = float(means.var(ddof=1) - (ses**2).mean())
    return Evidence("family_prior", m_k, max(tau2, cfg.tau_floor_annual**2))


def estimate(evidence: Sequence[Evidence]) -> EdgeEstimate:
    if not evidence:
        raise ValueError("at least one piece of evidence is required")
    precision = sum(1.0 / e.variance for e in evidence)
    mu = sum(e.value / e.variance for e in evidence) / precision
    variance = 1.0 / precision
    return EdgeEstimate(mu, variance, normal_cdf(mu / math.sqrt(variance)), tuple(e.kind for e in evidence))
