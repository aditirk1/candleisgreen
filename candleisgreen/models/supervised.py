"""Model levels B and C (spec Model laboratory). Each must beat the level below it out of sample.

Features per asset and day: time-series momentum, cross-sectional momentum, short-term
reversal and trailing volatility. Target: the next 21-day log return, demeaned across assets.
Training is walk-forward with a purge: a sample at day s is used to predict day t only when
its target window ended before t (s + horizon < t).
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge

from . import cross_sectional as xs

LEVEL_A = "level_a_momentum_ols"
LEVEL_B = "level_b_ridge"
LEVEL_C = "level_c_gbt"


def panel(prices: np.ndarray, horizon: int = 21) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Returns X of shape (T, N, F), y of shape (T, N), and feature names."""
    lr = np.diff(np.log(prices), axis=0, prepend=np.nan)
    vol = np.full_like(prices, np.nan)
    for t in range(63, prices.shape[0]):
        vol[t] = np.nanstd(lr[t - 62: t + 1], axis=0)
    feats = [xs.ts_momentum_raw(prices), xs.xs_momentum(prices), xs.st_reversal(prices), vol]
    X = np.stack(feats, axis=2)
    fwd = np.full_like(prices, np.nan)
    fwd[:-horizon] = np.log(prices[horizon:] / prices[:-horizon])
    y = fwd - np.nanmean(fwd, axis=1, keepdims=True)
    return X, y, ["ts_momentum", "xs_momentum", "st_reversal", "volatility"]


def walk_forward(X: np.ndarray, y: np.ndarray, make: Callable[[], object], features: list[int], start: int,
                 step: int, horizon: int) -> np.ndarray:
    """Predictions for every day from `start`, refit every `step` days on purged history."""
    T, N, _ = X.shape
    pred = np.full((T, N), np.nan)
    model = None
    for t in range(start, T):
        if model is None or (t - start) % step == 0:
            last_train = t - horizon - 1  # purge: the target of day s ends at s + horizon
            rows = [(s, i) for s in range(0, last_train + 1) for i in range(N)
                    if np.isfinite(X[s, i, features]).all() and np.isfinite(y[s, i])]
            if len(rows) < 50:
                continue
            Xs = np.array([X[s, i, features] for s, i in rows])
            ys = np.array([y[s, i] for s, i in rows])
            model = make()
            model.fit(Xs, ys)
        ok = np.isfinite(X[t][:, features]).all(axis=1)
        if model is not None and ok.any():
            pred[t, ok] = model.predict(X[t][ok][:, features])
    return pred


MODELS = {
    LEVEL_A: (lambda: LinearRegression(), [1]),
    LEVEL_B: (lambda: Ridge(alpha=1.0), [0, 1, 2, 3]),
    LEVEL_C: (lambda: HistGradientBoostingRegressor(max_iter=60, max_depth=3, learning_rate=0.05, random_state=0), [0, 1, 2, 3]),
}
