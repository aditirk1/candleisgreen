"""Spec C.10: the daily Composite run and its output record."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from ..core.config import AppConfig
from ..core.ids import make_id
from ..core.timeutil import ensure_utc
from ..data.pit_store import LookaheadError
from . import combine, edge, optimizer, weights
from .eligibility import SignalState, is_eligible


@dataclass(frozen=True)
class PaperRecord:
    r_paper: float  # annual in-sample return at 10% volatility
    se_paper: float
    group: str  # us_published, non_us_published, other_published
    modeled_cost: float  # annual cost at 10% volatility


@dataclass(frozen=True)
class SignalInput:
    state: SignalState
    z: np.ndarray  # standardized, smoothed score per asset today
    returns: np.ndarray  # daily net research returns after the selection cutoff
    oos_mean: float  # annual
    oos_se: float  # annual, Newey-West
    first_usable_at: datetime  # latest first_usable_at over every input of this signal
    paper: Optional[PaperRecord] = None


@dataclass(frozen=True)
class CalibrationInputs:
    realized_residual: np.ndarray
    forecast_unshrunk: np.ndarray
    daily_ic: np.ndarray
    n_oos_days: int
    backfilled: bool = True


@dataclass(frozen=True)
class BookInputs:
    """Everything the optimizer needs except alpha."""
    model: object
    x0: np.ndarray
    half_spread: np.ndarray
    sigma_daily: np.ndarray
    adv_usd: np.ndarray
    nav_usd: float
    sectors: tuple
    clusters: tuple


@dataclass(frozen=True)
class CompositeInputs:
    as_of: datetime
    asset_ids: tuple
    signals: tuple
    sigma_residual: np.ndarray  # 21-day residual volatility per asset
    calibration: Optional[CalibrationInputs] = None
    book: Optional[BookInputs] = None
    prev_weights: Optional[dict] = None
    frozen_weights: Optional[dict] = None


@dataclass(frozen=True)
class CompositeRun:
    composite_run_id: str
    as_of: datetime
    universe_hash: str
    config_hash: str
    signals: tuple  # one dict per signal
    unallocated_weight: float
    score: np.ndarray
    alpha: Optional[np.ndarray]
    calibration_status: str
    calibration_reasons: tuple
    optimizer_status: str
    target_weights: Optional[np.ndarray]
    ex_ante_vol_annual: Optional[float]
    contributions: np.ndarray  # signals x assets
    benchmarks: dict = field(default_factory=dict)


def _edge_for(index: int, signals: tuple, cfg) -> edge.EdgeEstimate:
    me = signals[index]
    others = [s for j, s in enumerate(signals) if j != index and s.state.family == me.state.family]
    evidence = [edge.family_prior([s.oos_mean for s in others], [s.oos_se for s in others], cfg)]
    if me.paper is not None:
        delta = edge.delta_for(me.paper.group, cfg)
        if delta is not None:
            evidence.append(edge.paper_evidence(me.paper.r_paper, me.paper.se_paper, delta, me.paper.modeled_cost, cfg))
    evidence.append(edge.oos_evidence(me.oos_mean, me.oos_se))
    return edge.estimate(evidence)


def daily(inputs: CompositeInputs, cfg: AppConfig) -> CompositeRun:
    as_of = ensure_utc(inputs.as_of)
    comp = cfg.composite
    late = [s.state.signal_id for s in inputs.signals if ensure_utc(s.first_usable_at) >= as_of]
    if late:
        raise LookaheadError(f"signal input(s) not usable before {as_of.isoformat()}: {', '.join(late)}")

    n_assets = len(inputs.asset_ids)
    edges = [_edge_for(i, inputs.signals, comp.edge) for i in range(len(inputs.signals))]
    verdicts = [is_eligible(s.state, e, comp.eligibility) for s, e in zip(inputs.signals, edges)]
    idx = [i for i, v in enumerate(verdicts) if v.eligible]

    shadow = np.zeros(len(inputs.signals))
    if idx:
        length = min(inputs.signals[i].returns.size for i in idx)
        returns = np.column_stack([inputs.signals[i].returns[-length:] for i in idx])
        prev = None
        if inputs.prev_weights is not None:
            prev = np.array([inputs.prev_weights.get(inputs.signals[i].state.signal_id, 0.0) for i in idx])
        result = weights.signal_weights(
            np.array([edges[i].mu_hat for i in idx]), returns,
            [inputs.signals[i].state.family for i in idx], comp.weights, prev,
        )
        shadow[idx] = result.weights
    capital = np.array([w if v.capital else 0.0 for w, v in zip(shadow, verdicts)])
    allocated = float(capital.sum())

    z = np.vstack([s.z for s in inputs.signals]) if inputs.signals else np.zeros((0, n_assets))
    scales = np.array([s.state.vol_scale for s in inputs.signals])
    score = combine.composite_score(z, capital, scales) if allocated > 0 else np.zeros(n_assets)
    contrib = combine.contributions(z, capital, scales) if inputs.signals else np.zeros((0, n_assets))

    cal = None
    if inputs.calibration is not None:
        c = inputs.calibration
        cal = combine.calibration(c.realized_residual, c.forecast_unshrunk, c.daily_ic, comp.alpha)
    calibrated = bool(cal and cal.calibrated and allocated > 0)
    cal_reasons = () if calibrated else (cal.reasons if cal else ("no calibration history",))
    if cal and cal.calibrated and allocated <= 0:
        cal_reasons = ("no signal holds capital weight",)

    alpha_vec = None
    if calibrated:
        alpha_vec = combine.alpha(score, inputs.sigma_residual, cal.ic_mean, inputs.calibration.n_oos_days, allocated, comp.alpha)

    target = vol = None
    opt_status = "not_run"
    if inputs.book is not None:
        b = inputs.book
        opt_in = optimizer.OptimizerInputs(
            alpha=alpha_vec if calibrated else np.zeros(n_assets), model=b.model, x0=b.x0,
            half_spread=b.half_spread, sigma_daily=b.sigma_daily, adv_usd=b.adv_usd, nav_usd=b.nav_usd,
            sectors=b.sectors, clusters=b.clusters,
        )
        res = optimizer.solve(opt_in, cfg.risk.hard_limits, comp.optimizer, reduce_only=not calibrated)
        target, vol, opt_status = res.weights, res.ex_ante_vol_annual, res.status

    # Benchmarks that run every day beside the live Composite.
    benchmarks = {}
    cap_idx = [i for i, v in enumerate(verdicts) if v.capital]
    challenger = np.zeros(len(inputs.signals))
    if cap_idx:
        challenger[cap_idx] = 1.0 / len(cap_idx)
    benchmarks["challenger_equal_weight"] = combine.composite_score(z, challenger, scales) if cap_idx else np.zeros(n_assets)
    frozen = np.array([(inputs.frozen_weights or {}).get(s.state.signal_id, 0.0) for s in inputs.signals])
    frozen = np.where([v.capital for v in verdicts], frozen, 0.0) if len(frozen) else frozen
    benchmarks["frozen_weight"] = combine.composite_score(z, frozen, scales) if frozen.sum() > 0 else np.zeros(n_assets)

    records = tuple(
        {
            "signal_id": s.state.signal_id, "family": s.state.family, "tier": s.state.tier,
            "mu_hat": e.mu_hat, "prob_positive": e.prob_positive, "weight": float(w),
            "capital_weight": float(cw), "eligible": v.eligible, "reasons": v.reasons,
        }
        for s, e, v, w, cw in zip(inputs.signals, edges, verdicts, shadow, capital)
    )
    universe_hash = make_id("univ", sorted(inputs.asset_ids))
    run_id = make_id("crun", {
        "as_of": as_of, "universe_hash": universe_hash, "config_hash": cfg.config_hash,
        "signals": [(r["signal_id"], r["tier"], round(r["weight"], 12)) for r in records],
        "score": [round(float(v), 12) for v in score],
    })
    return CompositeRun(
        composite_run_id=run_id, as_of=as_of, universe_hash=universe_hash, config_hash=cfg.config_hash,
        signals=records, unallocated_weight=float(max(0.0, 1.0 - allocated)), score=score, alpha=alpha_vec,
        calibration_status="calibrated" if calibrated else "signal_strength_only",
        calibration_reasons=tuple(cal_reasons), optimizer_status=opt_status, target_weights=target,
        ex_ante_vol_annual=vol, contributions=contrib, benchmarks=benchmarks,
    )
