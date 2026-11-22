"""Spec C.8: solve for target positions under the risk limits.

maximize  alpha'x - lambda x'Sigma x - sum_i ( c_i |dx_i| + kappa sigma_i sqrt(NAV/ADV_i) |dx_i|^1.5 )

Units: alpha and Sigma are at the alpha horizon (21 days). sigma_daily is daily volatility
and ADV is in dollars. Long-only, no leverage. The hard limits enter as constraints and
are re-applied to the solution, so the output can never break one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cvxpy as cp
import numpy as np

from ..core.config import HardLimits, OptimizerConfig
from .riskmodel import FactorModel

TOL = 1e-7


@dataclass(frozen=True)
class OptimizerInputs:
    alpha: np.ndarray
    model: FactorModel
    x0: np.ndarray
    half_spread: np.ndarray
    sigma_daily: np.ndarray
    adv_usd: np.ndarray
    nav_usd: float
    sectors: Sequence[str]
    clusters: Sequence[str]


@dataclass(frozen=True)
class OptimizerResult:
    weights: np.ndarray
    status: str  # optimal, vol_below_target, vol_target_unreachable, reduce_only, failed
    ex_ante_vol_annual: float
    lam: float
    solves: int


UNKNOWN = "UNKNOWN"


def _normalize(labels: Sequence[str]) -> np.ndarray:
    """Missing or blank labels share one UNKNOWN bucket, so they cannot evade a cap."""
    return np.array([str(x).strip() if x is not None and str(x).strip() else UNKNOWN for x in labels])


def _groups(labels: Sequence[str]) -> list[np.ndarray]:
    arr = _normalize(labels)
    return [np.where(arr == name)[0] for name in np.unique(arr)]


def _power15(expr):
    try:
        return cp.power(expr, 1.5, approx=False)  # exact power cone
    except TypeError:  # older cvxpy without the approx argument
        return cp.power(expr, 1.5)


def order_cap(inputs: OptimizerInputs, limits: HardLimits) -> np.ndarray:
    """Largest trade per name, as a fraction of equity, allowed by the ADV hard limit."""
    return limits.max_order_pct_adv20 * np.asarray(inputs.adv_usd, dtype=float) / inputs.nav_usd


def violations(x: np.ndarray, inputs: OptimizerInputs, limits: HardLimits, cfg: OptimizerConfig) -> list[str]:
    out = []
    if (x < -TOL).any():
        out.append("short position")
    if x.sum() > 1 + TOL:
        out.append("leverage")
    if (x > limits.max_position_pct_equity + TOL).any():
        out.append("position limit")
    if any(x[g].sum() > limits.max_cluster_pct_equity + TOL for g in _groups(inputs.clusters)):
        out.append("cluster limit")
    if any(x[g].sum() > cfg.sector_cap + TOL for g in _groups(inputs.sectors)):
        out.append("sector cap")
    if (np.abs(x - inputs.x0) > order_cap(inputs, limits) + TOL).any():
        out.append("order size limit")
    return out


def _project(x: np.ndarray, inputs: OptimizerInputs, limits: HardLimits, cfg: OptimizerConfig) -> np.ndarray:
    """Remove solver round-off. Every step only lowers weights."""
    x = np.clip(x, 0.0, limits.max_position_pct_equity)
    for groups, cap in ((_groups(inputs.clusters), limits.max_cluster_pct_equity), (_groups(inputs.sectors), cfg.sector_cap)):
        for g in groups:
            total = x[g].sum()
            if total > cap:
                x[g] *= cap / total
    if x.sum() > 1.0:
        x = x / x.sum()
    return x


def solve(inputs: OptimizerInputs, limits: HardLimits, cfg: OptimizerConfig, reduce_only: bool = False) -> OptimizerResult:
    n = inputs.alpha.size
    x0 = np.asarray(inputs.x0, dtype=float)
    model = inputs.model
    x = cp.Variable(n, nonneg=True)
    t = cp.Variable(n, nonneg=True)  # |x - x0|
    lam = cp.Parameter(nonneg=True)
    f_half = np.linalg.cholesky(model.factor_cov + 1e-14 * np.eye(model.factor_cov.shape[0]))
    risk = cp.sum_squares(f_half.T @ (model.loadings.T @ x)) + cp.sum_squares(cp.multiply(np.sqrt(model.specific_var), x))
    impact = cfg.impact_kappa * np.asarray(inputs.sigma_daily) * np.sqrt(inputs.nav_usd / np.asarray(inputs.adv_usd))
    alpha_vec = np.zeros(n) if reduce_only else np.asarray(inputs.alpha, dtype=float)
    objective = cp.Maximize(alpha_vec @ x - lam * risk - np.asarray(inputs.half_spread) @ t - impact @ _power15(t))
    cons = [
        t >= x - x0, t >= x0 - x, t <= order_cap(inputs, limits),
        cp.sum(x) <= 1.0, x <= limits.max_position_pct_equity,
    ]
    cons += [cp.sum(x[g]) <= limits.max_cluster_pct_equity for g in _groups(inputs.clusters)]
    cons += [cp.sum(x[g]) <= cfg.sector_cap for g in _groups(inputs.sectors)]
    if reduce_only:
        cons.append(x <= x0)
    problem = cp.Problem(objective, cons)
    solves = 0

    def run(value: float):
        nonlocal solves
        lam.value = value
        solves += 1
        try:
            problem.solve(solver=cp.CLARABEL)
        except cp.SolverError:
            return None
        if x.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
            return None
        return _project(np.asarray(x.value, dtype=float), inputs, limits, cfg)

    def vol(weights: np.ndarray) -> float:
        return model.annual_vol(weights)

    target = cfg.vol_target_annual
    best = run(cfg.lambda_min)
    status, lam_used = "optimal", cfg.lambda_min
    if best is None:
        return OptimizerResult(x0.copy(), "failed", vol(x0), float("nan"), solves)
    if vol(best) <= target:
        status = "vol_below_target" if vol(best) < target * 0.99 else "optimal"
    else:
        low, high = cfg.lambda_min, cfg.lambda_max
        top = run(high)
        if top is None:
            return OptimizerResult(x0.copy(), "failed", vol(x0), float("nan"), solves)
        best, lam_used = top, high
        if vol(top) > target:
            status = "vol_target_unreachable"
        else:
            for _ in range(cfg.lambda_bisection_iterations):
                mid = float(np.sqrt(low * high))
                cand = run(mid)
                if cand is None:
                    break
                if vol(cand) > target:
                    low = mid
                else:
                    high, best, lam_used = mid, cand, mid
                    if vol(cand) >= target * 0.99:
                        break
    # No-trade band: skip small trades when that breaks nothing.
    banded = np.where(np.abs(best - x0) < cfg.no_trade_band, x0, best)
    if not violations(banded, inputs, limits, cfg) and vol(banded) <= max(target, vol(best)) + 1e-9:
        if not (reduce_only and (banded > x0 + TOL).any()):
            best = banded
    if violations(best, inputs, limits, cfg):
        return OptimizerResult(x0.copy(), "failed", vol(x0), lam_used, solves)
    if reduce_only:
        status = "reduce_only"
    return OptimizerResult(best, status, vol(best), lam_used, solves)
