"""Level A cross-sectional baselines (MODEL_REGISTRY section 4). Raw scores on a price matrix.

Rows are days, columns are assets, values are adjusted closes. Row t uses rows up to t.
"""
from __future__ import annotations

import numpy as np

XS_MOMENTUM_ID = "xs_momentum_12_1"
ST_REVERSAL_ID = "st_reversal_5"


def xs_momentum(prices: np.ndarray, lookback: int = 252, skip: int = 21) -> np.ndarray:
    """Log return from t - lookback to t - skip. NaN until enough history."""
    p = np.asarray(prices, dtype=float)
    out = np.full_like(p, np.nan)
    if p.shape[0] > lookback:
        out[lookback:] = np.log(p[lookback - skip: p.shape[0] - skip] / p[: p.shape[0] - lookback])
    return out


def st_reversal(prices: np.ndarray, days: int = 5) -> np.ndarray:
    """Minus the log return over the last `days` days. Recent losers score high."""
    p = np.asarray(prices, dtype=float)
    out = np.full_like(p, np.nan)
    if p.shape[0] > days:
        out[days:] = -np.log(p[days:] / p[:-days])
    return out


def ts_momentum_raw(prices: np.ndarray, lookback: int = 252, skip: int = 21) -> np.ndarray:
    """Volatility-scaled trend per asset, the same score as models.ts_momentum, for every day."""
    p = np.asarray(prices, dtype=float)
    lr = np.diff(np.log(p), axis=0, prepend=np.nan)
    out = np.full_like(p, np.nan)
    for t in range(lookback, p.shape[0]):
        window = lr[t - lookback + 1: t - skip + 1]
        vol = np.nanstd(window, axis=0, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[t] = np.nansum(window, axis=0) / (vol * np.sqrt(window.shape[0]))
    return out
