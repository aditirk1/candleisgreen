"""Spec C.7: one score and one expected return per stock, and the calibration check."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr

from ..core.config import AlphaConfig
from .stats import newey_west_se


@dataclass(frozen=True)
class CalibrationResult:
    calibrated: bool
    slope: float
    ic_mean: float
    ic_t: float
    reasons: tuple[str, ...]


def normalized_scales(vol_scales: np.ndarray) -> np.ndarray:
    """g_s normalized to average 1."""
    g = np.asarray(vol_scales, dtype=float)
    return g / g.mean() if g.size and g.mean() > 0 else g


def composite_score(z: np.ndarray, weights: np.ndarray, vol_scales: np.ndarray) -> np.ndarray:
    """S_i = sum_s w_s g_s z_si, demeaned and scaled to unit standard deviation. z is S x N."""
    z = np.asarray(z, dtype=float)
    if z.shape[0] == 0:
        return np.zeros(z.shape[1] if z.ndim == 2 else 0)
    raw = (np.asarray(weights) * normalized_scales(vol_scales)) @ z
    raw = raw - raw.mean()
    std = raw.std()
    return raw / std if std > 0 else np.zeros_like(raw)


def contributions(z: np.ndarray, weights: np.ndarray, vol_scales: np.ndarray) -> np.ndarray:
    """Share of each signal in each asset's raw score. S x N, columns sum to 1 where defined."""
    parts = (np.asarray(weights) * normalized_scales(vol_scales))[:, None] * np.asarray(z, dtype=float)
    total = np.abs(parts).sum(axis=0)
    return np.divide(parts, total, out=np.zeros_like(parts), where=total > 0)


def ic_used(ic_mean: float, n_days: int, cfg: AlphaConfig) -> float:
    return ic_mean * n_days / (n_days + cfg.ic_shrink_days)


def unshrunk_forecast(score: np.ndarray, sigma: np.ndarray, ic_mean: float, cfg: AlphaConfig) -> np.ndarray:
    return ic_mean * np.asarray(sigma) * np.clip(score, -cfg.alpha_clip_sigmas, cfg.alpha_clip_sigmas)


def alpha(score: np.ndarray, sigma: np.ndarray, ic_mean: float, n_days: int, allocated: float, cfg: AlphaConfig):
    """alpha_i = IC_used x sigma_i x S_i, clipped at 3 sigma and scaled by the allocated weight."""
    clipped = np.clip(score, -cfg.alpha_clip_sigmas, cfg.alpha_clip_sigmas)
    return ic_used(ic_mean, n_days, cfg) * np.asarray(sigma) * clipped * allocated


def rank_ic(score: np.ndarray, realized: np.ndarray) -> float:
    ok = np.isfinite(score) & np.isfinite(realized)
    if ok.sum() < 3 or np.ptp(score[ok]) == 0 or np.ptp(realized[ok]) == 0:
        return 0.0
    return float(spearmanr(score[ok], realized[ok]).statistic)


def ic_statistics(daily_ic: np.ndarray, cfg: AlphaConfig) -> tuple[float, float]:
    """Mean IC and its t-statistic with Newey-West lag equal to the IC horizon."""
    daily_ic = np.asarray(daily_ic, dtype=float)
    if daily_ic.size < 2:
        return 0.0, 0.0
    mean = float(daily_ic.mean())
    se = newey_west_se(daily_ic, cfg.ic_horizon_days)
    return mean, (mean / se if se > 0 else 0.0)


def calibration(
    realized_residual: np.ndarray, forecast_unshrunk: np.ndarray, daily_ic: np.ndarray, cfg: AlphaConfig
) -> CalibrationResult:
    """Regress realized residual returns on the unshrunk forecast. Flat arrays, out of sample."""
    y = np.asarray(realized_residual, dtype=float).ravel()
    x = np.asarray(forecast_unshrunk, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    ic_mean, ic_t = ic_statistics(daily_ic, cfg)
    reasons: list[str] = []
    slope = float("nan")
    if ok.sum() < 3 or x[ok].var() == 0:
        reasons.append("not enough out-of-sample history")
    else:
        xc = x[ok] - x[ok].mean()
        slope = float(xc @ (y[ok] - y[ok].mean()) / (xc @ xc))
        if not (cfg.calibration_slope_min <= slope <= cfg.calibration_slope_max):
            reasons.append(f"slope {slope:.2f} outside {cfg.calibration_slope_min} to {cfg.calibration_slope_max}")
    if not ic_mean > 0:
        reasons.append("mean IC is not positive")
    if not ic_t > cfg.calibration_min_t:
        reasons.append(f"IC t-statistic {ic_t:.2f} not above {cfg.calibration_min_t}")
    return CalibrationResult(not reasons, slope, ic_mean, ic_t, tuple(reasons))
