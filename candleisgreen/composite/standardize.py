"""Spec C.2: turn raw signal values into comparable z-scores."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..core.config import StandardizeConfig

SMOOTHED_TYPES = ("cross_sectional", "time_series")


def _zscore(values: np.ndarray) -> np.ndarray:
    out = np.zeros_like(values, dtype=float)
    ok = np.isfinite(values)
    if ok.sum() < 2:
        return out
    std = values[ok].std()
    if std > 0:
        out[ok] = (values[ok] - values[ok].mean()) / std
    return out


def cross_sectional(raw: np.ndarray, cfg: StandardizeConfig, sectors: Optional[np.ndarray] = None) -> np.ndarray:
    """Winsorize at the configured percentiles, then z-score. Missing values become 0."""
    raw = np.asarray(raw, dtype=float)
    ok = np.isfinite(raw)
    clipped = raw.copy()
    if ok.sum() >= 2:
        lo, hi = np.percentile(raw[ok], [cfg.winsor_lower_pct, cfg.winsor_upper_pct])
        clipped[ok] = np.clip(raw[ok], lo, hi)
    if sectors is None:
        return _zscore(clipped)
    out = np.zeros_like(raw, dtype=float)
    sectors = np.asarray(sectors)
    for sector in np.unique(sectors):
        members = sectors == sector
        out[members] = _zscore(clipped[members])
    return out


def time_series(raw_history: np.ndarray, cfg: StandardizeConfig) -> np.ndarray:
    """Divide each asset's raw score by its own trailing standard deviation, then clip.

    `raw_history` is T x N. Row t uses rows up to and including t only.
    """
    raw = np.asarray(raw_history, dtype=float)
    out = np.zeros_like(raw)
    for t in range(raw.shape[0]):
        window = raw[max(0, t - cfg.ts_std_window_days + 1): t + 1]
        if window.shape[0] < 2:
            continue
        std = np.nanstd(window, axis=0)
        ok = np.isfinite(raw[t]) & (std > 0)
        out[t, ok] = np.clip(raw[t, ok] / std[ok], -cfg.ts_clip, cfg.ts_clip)
    return out


def smooth(z_history: np.ndarray, horizon_days: int, signal_type: str, cfg: StandardizeConfig) -> np.ndarray:
    """EMA with half-life fraction x horizon. The only smoothing step.

    Event and practitioner signals are returned unchanged, so they stay zero outside
    their window. Cross-sectional scores are standardized again after smoothing.
    """
    z = np.nan_to_num(np.asarray(z_history, dtype=float), nan=0.0)
    if signal_type not in SMOOTHED_TYPES:
        return z
    half_life = max(cfg.ema_halflife_fraction_of_horizon * horizon_days, 1e-9)
    decay = 0.5 ** (1.0 / half_life)
    out = np.empty_like(z)
    out[0] = z[0]
    for t in range(1, z.shape[0]):
        out[t] = decay * out[t - 1] + (1.0 - decay) * z[t]
    if signal_type == "cross_sectional":
        for t in range(out.shape[0]):
            active = z[t] != 0  # assets with no view stay at zero
            row = np.where(active | (out[t] != 0), out[t], np.nan)
            out[t] = _zscore(row)
    return out


def apply_event_window(z: np.ndarray, in_window: np.ndarray) -> np.ndarray:
    """Force an event signal to zero outside its window."""
    return np.where(np.asarray(in_window, dtype=bool), np.asarray(z, dtype=float), 0.0)


def practitioner_claim(direction: int, confidence: float, days_since: int, horizon_days: int) -> float:
    """Spec C.9: +1 or -1 times stated confidence, decaying linearly to 0 over the horizon."""
    if direction not in (-1, 1):
        raise ValueError("direction must be +1 or -1")
    if days_since < 0 or days_since >= horizon_days:
        return 0.0
    return direction * float(np.clip(confidence, 0.0, 1.0)) * (1.0 - days_since / horizon_days)
