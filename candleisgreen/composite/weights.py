"""Spec C.6: weight the signals so correlated signals share a budget."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import nnls
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

from ..core.config import WeightConfig


@dataclass(frozen=True)
class WeightResult:
    weights: np.ndarray  # final w_s per signal, sums to at most 1
    unallocated: float
    family_weights: dict
    pre_cap: np.ndarray  # w_s before caps and the change limit


def shrunk_cov(returns: np.ndarray) -> np.ndarray:
    return LedoitWolf().fit(np.asarray(returns, dtype=float)).covariance_


def duplicate_groups(returns: np.ndarray, threshold: float) -> list[list[int]]:
    """Group signals whose return correlation is above the threshold."""
    k = returns.shape[1]
    if k == 1:
        return [[0]]
    corr = np.corrcoef(returns, rowvar=False)
    groups: list[list[int]] = []
    assigned = [-1] * k
    for i in range(k):
        if assigned[i] >= 0:
            continue
        assigned[i] = len(groups)
        members = [i]
        for j in range(i + 1, k):
            if assigned[j] < 0 and corr[i, j] > threshold:
                assigned[j] = assigned[i]
                members.append(j)
        groups.append(members)
    return groups


def _nonneg_mean_variance(mu: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """min w'Cw - 2 w'mu subject to w >= 0, solved as non-negative least squares."""
    chol = np.linalg.cholesky(cov + 1e-12 * np.eye(cov.shape[0]))
    w, _ = nnls(chol.T, np.linalg.solve(chol, mu))
    return w


def within_family(mu: np.ndarray, returns: np.ndarray, cfg: WeightConfig) -> np.ndarray:
    """Weights inside one family, summing to 1. `returns` is T x K daily signal returns."""
    mu = np.asarray(mu, dtype=float)
    returns = np.asarray(returns, dtype=float)[-cfg.cov_window_days:]
    k = mu.size
    if k == 1:
        return np.ones(1)
    groups = duplicate_groups(returns, cfg.duplicate_correlation_threshold)
    g_returns = np.column_stack([returns[:, g].mean(axis=1) for g in groups])
    g_mu = np.array([mu[g].mean() for g in groups])
    if len(groups) <= 2 or returns.shape[0] < cfg.cov_min_days:
        raw = np.maximum(g_mu, 0.0) / g_returns.var(axis=0, ddof=1)
    else:
        raw = _nonneg_mean_variance(g_mu, shrunk_cov(g_returns))
    if raw.sum() <= 0:
        raw = np.ones(len(groups))
    raw = raw / raw.sum()
    out = np.zeros(k)
    for weight, members in zip(raw, groups):
        out[members] = weight / len(members)
    return out


def hierarchical_risk_parity(returns: np.ndarray) -> np.ndarray:
    """Lopez de Prado (2016): cluster, quasi-diagonalize, recursive bisection."""
    cov = np.cov(returns, rowvar=False)
    std = np.sqrt(np.diag(cov))
    corr = np.clip(cov / np.outer(std, std), -1.0, 1.0)
    dist = np.sqrt(0.5 * (1.0 - corr))
    np.fill_diagonal(dist, 0.0)
    order = list(leaves_list(linkage(squareform(dist, checks=False), method="single")))
    weights = np.ones(cov.shape[0])
    clusters = [order]
    while clusters:
        nxt = []
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            half = len(cluster) // 2
            left, right = cluster[:half], cluster[half:]

            def cluster_var(items):
                sub = cov[np.ix_(items, items)]
                ivp = 1.0 / np.diag(sub)
                ivp /= ivp.sum()
                return float(ivp @ sub @ ivp)

            var_left, var_right = cluster_var(left), cluster_var(right)
            share_left = 1.0 - var_left / (var_left + var_right)
            weights[left] *= share_left
            weights[right] *= 1.0 - share_left
            nxt += [left, right]
        clusters = nxt
    return weights / weights.sum()


def across_families(family_returns: np.ndarray, cfg: WeightConfig) -> np.ndarray:
    family_returns = np.asarray(family_returns, dtype=float)[-cfg.cov_window_days:]
    count = family_returns.shape[1]
    if count == 1:
        return np.ones(1)
    if count < cfg.hrp_min_families:
        inv = 1.0 / family_returns.var(axis=0, ddof=1)
        return inv / inv.sum()
    return hierarchical_risk_parity(family_returns)


def apply_caps(weights: np.ndarray, families: Sequence[str], cfg: WeightConfig) -> tuple[np.ndarray, float]:
    """Signal and family caps. Excess goes to uncapped signals. Weights may sum to under 1."""
    w = np.asarray(weights, dtype=float).copy()
    fam = np.asarray(families)
    budget = float(w.sum())
    frozen = np.zeros(w.size, dtype=bool)
    for _ in range(4 * w.size + 8):
        over = (w > cfg.signal_cap + 1e-12) & ~frozen
        w[over] = cfg.signal_cap
        frozen |= over
        for name in np.unique(fam):
            members = fam == name
            total = w[members].sum()
            if total > cfg.family_cap + 1e-12:
                w[members] *= cfg.family_cap / total
                frozen |= members
        excess = budget - w.sum()
        free = ~frozen & (w > 0)
        if excess <= 1e-12 or not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return w, float(max(0.0, 1.0 - w.sum()))


def limit_change(
    new: np.ndarray,
    prev: Optional[np.ndarray],
    cfg: WeightConfig,
    removed: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Monthly change limit. Entries are capped, removals are immediate and exempt."""
    new = np.asarray(new, dtype=float).copy()
    if prev is None:
        return new
    prev = np.asarray(prev, dtype=float)
    band = np.maximum(cfg.max_monthly_relative_change * prev, cfg.max_monthly_absolute_change_floor)
    out = np.clip(new, np.maximum(prev - band, 0.0), prev + band)
    entering = prev <= 0
    out[entering] = np.minimum(new[entering], cfg.new_signal_initial_weight_max)
    if removed is not None:
        out[np.asarray(removed, dtype=bool)] = 0.0
    total = out.sum()
    return out / total if total > 1.0 else out


def signal_weights(
    mu: np.ndarray,
    returns: np.ndarray,
    families: Sequence[str],
    cfg: WeightConfig,
    prev: Optional[np.ndarray] = None,
    removed: Optional[np.ndarray] = None,
) -> WeightResult:
    """Full C.6 pipeline for the eligible signals. `returns` is T x S."""
    mu = np.asarray(mu, dtype=float)
    returns = np.asarray(returns, dtype=float)
    fam = np.asarray(families)
    if mu.size == 0:
        return WeightResult(np.zeros(0), 1.0, {}, np.zeros(0))
    names = list(dict.fromkeys(families))
    within = np.zeros(mu.size)
    family_series = []
    for name in names:
        members = np.where(fam == name)[0]
        w = within_family(mu[members], returns[:, members], cfg)
        within[members] = w
        family_series.append(returns[:, members] @ w)
    family_w = across_families(np.column_stack(family_series), cfg)
    pre_cap = np.zeros(mu.size)
    for weight, name in zip(family_w, names):
        pre_cap[fam == name] = weight * within[fam == name]
    capped, _ = apply_caps(pre_cap, families, cfg)
    final = limit_change(capped, prev, cfg, removed)
    return WeightResult(final, float(max(0.0, 1.0 - final.sum())), dict(zip(names, family_w.tolist())), pre_cap)
