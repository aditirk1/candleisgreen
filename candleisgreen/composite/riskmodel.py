"""Spec C.8 risk model: statistical factor model, Sigma = B F B' + D."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.covariance import LedoitWolf

from ..core.config import OptimizerConfig


@dataclass(frozen=True)
class FactorModel:
    loadings: np.ndarray  # B, N x K
    factor_cov: np.ndarray  # F, K x K, at the alpha horizon
    specific_var: np.ndarray  # D diagonal, length N, at the alpha horizon
    horizon_days: int

    def covariance(self) -> np.ndarray:
        return self.loadings @ self.factor_cov @ self.loadings.T + np.diag(self.specific_var)

    def portfolio_variance(self, x: np.ndarray) -> float:
        exposure = self.loadings.T @ x
        return float(exposure @ self.factor_cov @ exposure + (self.specific_var * x * x).sum())

    def annual_vol(self, x: np.ndarray, days_per_year: int = 252) -> float:
        return float(np.sqrt(self.portfolio_variance(x) * days_per_year / self.horizon_days))


def fit(daily_returns: np.ndarray, cfg: OptimizerConfig) -> FactorModel:
    """Fit on the last `cov_window_days` rows of a T x N matrix. NaN marks missing history."""
    r = np.asarray(daily_returns, dtype=float)[-cfg.cov_window_days:]
    history = np.isfinite(r).sum(axis=0)
    seasoned = history >= min(cfg.min_history_days, r.shape[0])
    filled = np.where(np.isfinite(r), r, 0.0)
    centered = filled - filled.mean(axis=0)
    k = int(min(cfg.n_factors, max(1, seasoned.sum() - 1), r.shape[0] - 1))
    _, _, vt = np.linalg.svd(centered[:, seasoned], full_matrices=False)
    basis = vt[:k].T  # seasoned assets x K
    factors = centered[:, seasoned] @ basis  # T x K
    loadings = np.zeros((r.shape[1], k))
    loadings[seasoned] = basis
    if (~seasoned).any():
        loadings[~seasoned] = basis.mean(axis=0)  # average loadings for short histories
    factor_cov = LedoitWolf().fit(factors).covariance_ if k > 1 else np.atleast_2d(factors.var(ddof=1))
    resid = centered - factors @ loadings.T
    specific = resid.var(axis=0, ddof=1)
    median = float(np.median(specific[seasoned]))
    specific = (1.0 - cfg.specific_var_shrink) * specific + cfg.specific_var_shrink * median
    specific[~seasoned] = median
    h = cfg.alpha_horizon_days
    return FactorModel(loadings, factor_cov * h, specific * h, h)
