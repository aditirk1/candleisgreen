"""Small statistics helpers used by the Composite. Pure numpy."""
from __future__ import annotations

import math

import numpy as np


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def newey_west_se(x: np.ndarray, lag: int) -> float:
    """Standard error of the mean of x with Bartlett weights up to `lag`."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 2:
        return float("nan")
    lag = int(max(0, min(lag, n - 1)))
    d = x - x.mean()
    long_run = float(d @ d) / n
    for k in range(1, lag + 1):
        weight = 1.0 - k / (lag + 1.0)
        long_run += 2.0 * weight * float(d[k:] @ d[:-k]) / n
    return math.sqrt(max(long_run, 0.0) / n)


def nw_lag(horizon_days: int, n_obs: int, max_lag: int) -> int:
    """Spec C.3: lag = min(h_s, max_lag, T / 4)."""
    return int(max(0, min(horizon_days, max_lag, n_obs // 4)))


def annualized_mean_and_se(daily: np.ndarray, horizon_days: int, max_lag: int, days_per_year: int):
    """Return (annual mean, its Newey-West standard error, annual variance)."""
    daily = np.asarray(daily, dtype=float)
    lag = nw_lag(horizon_days, daily.size, max_lag)
    mean = float(daily.mean()) * days_per_year
    se = newey_west_se(daily, lag) * days_per_year
    var = float(daily.var(ddof=1)) * days_per_year if daily.size > 1 else float("nan")
    return mean, se, var


def block_bootstrap_mean_interval(
    daily: np.ndarray, block: int, resamples: int, level: float, rng: np.random.Generator
) -> tuple[float, float]:
    """Circular block bootstrap interval for the mean of a daily series."""
    daily = np.asarray(daily, dtype=float)
    n = daily.size
    block = int(max(1, min(block, n)))
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(resamples, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    means = daily[idx.reshape(resamples, -1)[:, :n]].mean(axis=1)
    tail = (1.0 - level) / 2.0
    return float(np.quantile(means, tail)), float(np.quantile(means, 1.0 - tail))
