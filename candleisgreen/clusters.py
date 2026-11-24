"""Correlation clusters for the cluster exposure limit (spec decision Q7).

Monthly job:
1. Daily returns from split-adjusted closes known at the run time, over `clustering.lookback_days`.
2. Residuals after removing an equal-weighted market return, so the market factor does not put
   every stock in one cluster.
3. Average-linkage clustering on the correlation distance sqrt((1 - rho) / 2), cut at
   `clustering.max_distance`.
4. Stability: adjusted Rand index against the previous run on the names both share. Below
   `clustering.min_stability`, the run is UNSTABLE and orders fall back to sector clusters.

Order-time lookup (`cluster_key`):
- A STABLE run: the name's cluster. A name the run did not cover has no cluster and the risk
  check blocks it, as Q7's failure behavior requires.
- No run yet, or an UNSTABLE latest run: the name's Fama-French 12 sector, with unknown sectors
  pooled into one bucket. This is the sector-limit fallback.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.metrics import adjusted_rand_score

from .core.config import AppConfig, ClusteringConfig
from .core.ids import make_id
from .core.timeutil import ensure_utc, from_micros, to_micros
from .data.adjust import adjust_closes
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore

_DDL = """
CREATE TABLE IF NOT EXISTS cluster_runs (
    run_id VARCHAR PRIMARY KEY, as_of BIGINT NOT NULL, names INTEGER NOT NULL, clusters INTEGER NOT NULL,
    stability DOUBLE, status VARCHAR NOT NULL, detail VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS cluster_members (
    run_id VARCHAR NOT NULL, instrument_id VARCHAR NOT NULL, cluster VARCHAR NOT NULL,
    PRIMARY KEY (run_id, instrument_id)
);
"""
STABLE, UNSTABLE, FIRST = "STABLE", "UNSTABLE", "FIRST_RUN"


@dataclass(frozen=True)
class ClusterRun:
    run_id: str
    as_of: datetime
    labels: dict[str, str]
    stability: Optional[float]
    status: str
    detail: dict


def residual_returns(returns: np.ndarray) -> np.ndarray:
    """Remove each name's exposure to the equal-weighted market return. Rows are days."""
    market = returns.mean(axis=1, keepdims=True)
    m = market - market.mean()
    r = returns - returns.mean(axis=0, keepdims=True)
    beta = (m * r).sum(axis=0) / max(float((m * m).sum()), 1e-18)
    return r - m * beta


def cluster_labels(residuals: np.ndarray, max_distance: float) -> np.ndarray:
    """Average linkage on sqrt((1 - rho) / 2). Returns integer labels from 1."""
    n = residuals.shape[1]
    if n == 1:
        return np.array([1])
    rho = np.corrcoef(residuals, rowvar=False)
    rho = np.nan_to_num(rho, nan=0.0)
    np.fill_diagonal(rho, 1.0)
    dist = np.sqrt(np.clip((1.0 - rho) / 2.0, 0.0, 1.0))
    np.fill_diagonal(dist, 0.0)
    z = linkage(squareform(dist, checks=False), method="average")
    return fcluster(z, t=max_distance, criterion="distance")


def stability(previous: dict[str, str], current: dict[str, str]) -> Optional[float]:
    """Adjusted Rand index on the names both runs cover. None when fewer than three are shared."""
    common = sorted(set(previous) & set(current))
    if len(common) < 3:
        return None
    return float(adjusted_rand_score([previous[i] for i in common], [current[i] for i in common]))


def _ensure(store: PointInTimeStore) -> None:
    for stmt in _DDL.strip().split(";"):
        if stmt.strip():
            store.connection.execute(stmt).fetchall()


def latest_run(conn) -> Optional[ClusterRun]:
    try:
        rows = conn.execute("SELECT run_id, as_of, stability, status, detail FROM cluster_runs "
                            "ORDER BY as_of DESC LIMIT 1").fetchall()
    except Exception:
        return None  # no table yet
    if not rows:
        return None
    run_id, as_of, stab, status, detail = rows[0]
    labels = dict(conn.execute("SELECT instrument_id, cluster FROM cluster_members WHERE run_id = ?",
                               [run_id]).fetchall())
    return ClusterRun(run_id, from_micros(as_of), labels, stab, status, json.loads(detail))


def last_stable_labels(conn) -> dict[str, str]:
    rows = conn.execute("SELECT run_id FROM cluster_runs WHERE status IN (?, ?) ORDER BY as_of DESC LIMIT 1",
                        [STABLE, FIRST]).fetchall()
    if not rows:
        return {}
    return dict(conn.execute("SELECT instrument_id, cluster FROM cluster_members WHERE run_id = ?", [rows[0][0]]).fetchall())


def run(as_of: datetime, store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig,
        force: bool = False) -> ClusterRun:
    """Compute and store one clustering. Safe to rerun: a recent run is returned unchanged."""
    c = cfg.clustering
    as_of = ensure_utc(as_of)
    _ensure(store)
    prev = latest_run(store.connection)
    if prev and not force and as_of - prev.as_of < timedelta(days=c.refresh_days):
        return prev
    view = store.as_of(as_of)
    series: dict[str, dict] = {}
    for inst in master.instruments():
        iid = inst["instrument_id"]
        obs = view.series(iid, "close")[-(c.lookback_days + 1):]
        if len(obs) < c.min_observations + 1:
            continue
        adj = adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(iid), as_of.date())
        series[iid] = dict(adj)
    dates = sorted(set().union(*[set(s) for s in series.values()])) if series else []
    ids = sorted(series)
    detail: dict = {"lookback_days": c.lookback_days, "max_distance": c.max_distance, "method": "average linkage"}
    if len(ids) < 2 or len(dates) < c.min_observations + 1:
        labels = {i: f"c{n + 1}" for n, i in enumerate(ids)}
        stab, status = None, FIRST if prev is None else UNSTABLE
        detail["note"] = "too few names or days to cluster"
    else:
        prices = np.array([[series[i].get(d, np.nan) for i in ids] for d in dates], dtype=float)
        rets = prices[1:] / prices[:-1] - 1.0
        keep = ~np.isnan(rets).any(axis=1)
        rets = rets[keep]
        raw = cluster_labels(residual_returns(rets), c.max_distance)
        labels = {i: f"c{int(k)}" for i, k in zip(ids, raw)}
        reference = last_stable_labels(store.connection)
        stab = stability(reference, labels) if reference else None
        if not reference:
            status = FIRST
        elif stab is None or stab < c.min_stability:
            status = UNSTABLE
        else:
            status = STABLE
        detail["days_used"] = int(rets.shape[0])
    run_id = make_id("clu", {"as_of": as_of, "labels": labels})
    store.connection.execute("INSERT OR REPLACE INTO cluster_runs VALUES (?,?,?,?,?,?,?)",
                             [run_id, to_micros(as_of), len(labels), len(set(labels.values())), stab, status,
                              json.dumps(detail)]).fetchall()
    if labels:
        store.connection.executemany("INSERT OR REPLACE INTO cluster_members VALUES (?,?,?)",
                                     [[run_id, i, k] for i, k in labels.items()])
    return ClusterRun(run_id, as_of, labels, stab, status, detail)


def cluster_key(conn, master: InstrumentMaster, instrument_id: str, when: datetime) -> tuple[Optional[str], str]:
    """The cluster used by the order-time limit, and which mode produced it.

    Returns (None, mode) when a stable clustering does not cover the name. The order is then blocked.
    """
    last = latest_run(conn)
    if last is None or last.status == UNSTABLE:
        sector = master.sector_at(instrument_id, when) or "UNKNOWN"
        return f"sector:{sector}", "sector fallback"
    return (last.labels.get(instrument_id), f"clusters {last.run_id}")


def config_for_tests(cfg: AppConfig, **changes) -> AppConfig:
    return cfg.model_copy(update={"clustering": cfg.clustering.model_copy(update=changes)})


__all__ = ["ClusterRun", "ClusteringConfig", "cluster_key", "cluster_labels", "latest_run", "residual_returns", "run",
           "stability"]
