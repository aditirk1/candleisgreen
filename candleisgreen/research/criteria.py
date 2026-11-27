"""Decision criteria by study type (spec Research pipeline). Every threshold is provisional
except the t of 3.0 for new factors, which is empirical (Harvey, Liu and Zhu) and applies
to that case only."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.stats import norm, t as student_t

from ..composite.stats import newey_west_se
from ..core.config import CriteriaConfig


def benjamini_yekutieli(pvalues: Sequence[float], level: float) -> list[bool]:
    """FDR control under arbitrary dependence. Returns which hypotheses are rejected."""
    p = np.asarray(pvalues, dtype=float)
    m = p.size
    if m == 0:
        return []
    c_m = sum(1.0 / i for i in range(1, m + 1))
    order = np.argsort(p)
    thresholds = level * np.arange(1, m + 1) / (m * c_m)
    passed = p[order] <= thresholds
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    reject = np.zeros(m, dtype=bool)
    reject[order[:k]] = True
    return reject.tolist()


@dataclass(frozen=True)
class TestResult:
    statistic: float
    pvalue: float
    passed: bool
    detail: str


def diebold_mariano(loss_baseline: np.ndarray, loss_model: np.ndarray, horizon: int, level: float) -> TestResult:
    """One-sided test that the model has lower loss, with the Harvey-Leybourne-Newbold correction.
    For non-nested comparisons only."""
    d = np.asarray(loss_baseline, dtype=float) - np.asarray(loss_model, dtype=float)
    n = d.size
    se = newey_west_se(d, max(horizon - 1, 0))
    dm = d.mean() / se if se > 0 else 0.0
    hln = math.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    stat = dm * hln
    p = 1 - student_t.cdf(stat, df=n - 1)
    return TestResult(stat, p, p < level, "Diebold-Mariano with Harvey-Leybourne-Newbold correction")


def clark_west(y: np.ndarray, f_baseline: np.ndarray, f_model: np.ndarray, horizon: int, level: float) -> TestResult:
    """One-sided test for a model that nests its baseline (Clark and West 2007)."""
    y, f1, f2 = (np.asarray(a, dtype=float) for a in (y, f_baseline, f_model))
    adj = (y - f1) ** 2 - ((y - f2) ** 2 - (f1 - f2) ** 2)
    se = newey_west_se(adj, max(horizon - 1, 0))
    stat = adj.mean() / se if se > 0 else 0.0
    p = 1 - norm.cdf(stat)
    return TestResult(stat, p, p < level, "Clark-West adjusted mean squared error")


def forecast_beats_baseline(y: np.ndarray, f_baseline: np.ndarray, f_model: np.ndarray, horizon: int, nested: bool,
                            cfg: CriteriaConfig) -> dict:
    """Spec rule: beats its baseline out of sample at one-sided 5% and holds in at least two of
    three subperiods. Clark-West when nested, Diebold-Mariano otherwise."""
    y, f1, f2 = (np.asarray(a, dtype=float) for a in (y, f_baseline, f_model))

    def run(a, b, c):
        if nested:
            return clark_west(a, b, c, horizon, cfg.forecast_significance)
        return diebold_mariano((a - b) ** 2, (a - c) ** 2, horizon, cfg.forecast_significance)

    full = run(y, f1, f2)
    parts = np.array_split(np.arange(y.size), cfg.forecast_subperiods)
    held = sum(1 for idx in parts if ((y[idx] - f1[idx]) ** 2).mean() > ((y[idx] - f2[idx]) ** 2).mean())
    passed = full.passed and held >= cfg.forecast_min_subperiods_passed
    return {"test": full.detail, "statistic": round(full.statistic, 4), "pvalue": round(full.pvalue, 5),
            "subperiods_held": held, "subperiods": cfg.forecast_subperiods, "passed": bool(passed)}


def new_factor_passes(t_stat: float, pvalue: float, registry_pvalues: Sequence[float], holdout_passed: bool,
                      cfg: CriteriaConfig) -> dict:
    """Spec rule for a factor found by the platform's own search: t above 3.0, and FDR under 5%
    across the full trial registry (Benjamini-Yekutieli), and a pass on an untouched holdout."""
    pvals = list(registry_pvalues) + [pvalue]
    fdr_ok = benjamini_yekutieli(pvals, cfg.fdr_level)[-1]
    return {"t_ok": t_stat > cfg.new_factor_min_t, "fdr_ok": bool(fdr_ok), "holdout_ok": holdout_passed,
            "trials": len(pvals), "passed": bool(t_stat > cfg.new_factor_min_t and fdr_ok and holdout_passed)}


def event_study(abnormal_returns: np.ndarray, clusters: np.ndarray, cfg: CriteriaConfig) -> dict:
    """Mean abnormal return with standard errors clustered by event date. Passes when the
    two-sided interval excludes zero."""
    ar = np.asarray(abnormal_returns, dtype=float)
    cl = np.asarray(clusters)
    mean = ar.mean()
    groups = [ar[cl == c] - mean for c in np.unique(cl)]
    g = len(groups)
    var = sum(x.sum() ** 2 for x in groups) / ar.size ** 2 * (g / (g - 1) if g > 1 else 1.0)
    se = math.sqrt(var)
    z = norm.ppf(1 - cfg.event_significance / 2)
    lo, hi = mean - z * se, mean + z * se
    p = 2 * (1 - norm.cdf(abs(mean / se))) if se > 0 else 1.0
    return {"mean": mean, "interval": [lo, hi], "pvalue": p, "clusters": g, "passed": bool(lo > 0 or hi < 0)}
