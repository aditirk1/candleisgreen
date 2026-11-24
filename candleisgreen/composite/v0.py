"""Composite v0 (spec Phase 3): three Level A signals through every Composite step.

Platform history is reconstructed by walk-forward, so its records are RETROSPECTIVE
(decision Q9). Results on the offline market are labeled SYNTHETIC, and results on Alpaca
history before the forward record are labeled SURVIVORSHIP-BIASED. Neither can pass a gate.
Every signal record carries its evidence chain so the screen can show it.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np

from ..core.config import AppConfig
from ..core.parameters import load_registry
from ..core.timeutil import ensure_utc, local_to_utc
from ..data.adjust import adjust_closes
from ..data.instruments import InstrumentMaster
from ..data.pit_store import PointInTimeStore
from ..models import cross_sectional as xs
from ..research.registry import ResearchRegistry
from . import research_portfolio, run, standardize
from .eligibility import SignalState, economic_test
from .stats import annualized_mean_and_se

SIGNALS = {
    "ts_momentum_252_21": {"family": "trend", "type": "time_series", "horizon": 21, "claim": None},
    xs.XS_MOMENTUM_ID: {"family": "momentum", "type": "cross_sectional", "horizon": 21, "claim": "Mom12m"},
    xs.ST_REVERSAL_ID: {"family": "short_term_reversal", "type": "cross_sectional", "horizon": 5, "claim": "STreversal"},
}


def _matrix(store: PointInTimeStore, master: InstrumentMaster, as_of: datetime, decision_date: date,
            min_days: int = 30):
    view = store.as_of(as_of)
    series, vols, vendors, ids = {}, {}, set(), []
    for inst in master.instruments():
        iid = inst["instrument_id"]
        closes = view.series(iid, "close")
        if len(closes) < min_days:
            continue
        adj = adjust_closes([(o.event_time.date(), o.value) for o in closes], master.actions(iid), decision_date)
        series[iid] = dict(adj)
        vols[iid] = {o.event_time.date(): o.value for o in view.series(iid, "volume")}
        vendors |= {o.vendor for o in closes}
        ids.append(iid)
    days = sorted(set().union(*[set(s) for s in series.values()])) if series else []
    prices = np.array([[series[i].get(d, np.nan) for i in ids] for d in days], dtype=float)
    volume = np.array([[vols[i].get(d, np.nan) for i in ids] for d in days], dtype=float)
    return ids, days, prices, volume, vendors


def build(store: PointInTimeStore, master: InstrumentMaster, registry: ResearchRegistry, cfg: AppConfig,
          decision_date: date, now: datetime) -> dict:
    as_of = local_to_utc(decision_date, cfg.time.decision_time_local, cfg.time.market_timezone)
    ids, days, prices, volume, vendors = _matrix(store, master, as_of, decision_date, cfg.composite.min_history_days)
    if len(ids) < 2 or len(days) < cfg.composite.min_history_days:
        return {"status": "NOT AVAILABLE", "as_of": as_of.isoformat(),
                "reason": f"{len(ids)} names with at least {cfg.composite.min_history_days} recorded closes. The run needs two or more"}
    synthetic = any(v.endswith("synthetic") for v in vendors)
    labels = ("SYNTHETIC",) if synthetic else ("SURVIVORSHIP-BIASED",)
    comp = cfg.composite
    rets = np.vstack([np.diff(prices, axis=0) / prices[:-1], np.full((1, prices.shape[1]), np.nan)])  # next-day return
    sigma = np.vstack([np.full((1, prices.shape[1]), np.nan), rets[:-1]])
    sigma_daily = np.array([np.nanstd(sigma[max(0, t - 63): t + 1], axis=0) for t in range(len(days))])
    market = research_portfolio.MarketInputs(
        returns=np.nan_to_num(rets), half_spread=np.full(prices.shape, cfg.research.default_half_spread),
        sigma_daily=np.nan_to_num(sigma_daily, nan=0.02), adv_usd=np.nan_to_num(prices * volume, nan=1.0),
        price=np.nan_to_num(prices, nan=1.0))
    raws = {"ts_momentum_252_21": xs.ts_momentum_raw(prices), xs.XS_MOMENTUM_ID: xs.xs_momentum(prices),
            xs.ST_REVERSAL_ID: xs.st_reversal(prices)}
    inputs, evidence = [], {}
    for sid, meta in SIGNALS.items():
        raw = raws[sid]
        if meta["type"] == "cross_sectional":
            z = np.vstack([standardize.cross_sectional(row, comp.standardize) for row in raw])
        else:
            z = standardize.time_series(raw, comp.standardize)
        z = standardize.smooth(z, meta["horizon"], meta["type"], comp.standardize)
        series = research_portfolio.build(z, meta["type"], market, comp)
        net = series.net[series.active]
        tier, status, tier_ev = registry.tier(sid)
        if net.size > 30:
            mean, se, _ = annualized_mean_and_se(net, meta["horizon"], comp.research_portfolio.newey_west_max_lag_days,
                                                 comp.research_portfolio.trading_days_per_year)
            elig = comp.eligibility.model_copy(update={"bootstrap_resamples": 500})
            lower, econ_pass = economic_test(net, series.cost[series.active], elig, np.random.default_rng(7))
        else:
            mean, se, lower, econ_pass = 0.0, 1.0, None, False
        acad = tier_ev.get("academic_record")
        state = SignalState(sid, meta["family"], meta["type"], meta["horizon"], tier, int(net.size),
                            vol_scale=series.vol_scale if net.size else 1.0, data_labels=labels)
        inputs.append(run.SignalInput(
            state=state, z=np.nan_to_num(z[-1]), returns=net if net.size else np.zeros(2), oos_mean=mean,
            oos_se=max(se, 1e-6), first_usable_at=as_of - timedelta(seconds=1),
            academic=run.AcademicRecord(acad["mean"], acad["se"], 0.0, acad["license"]) if acad else None))
        evidence[sid] = {
            "tier": tier, "status": status, "claim": meta["claim"], "claim_id": tier_ev.get("claim_id"),
            "experiments": [e for e in (tier_ev.get("reproduction"), tier_ev.get("replication")) if e],
            "academic_record": acad, "data_labels": list(labels), "record_type": "retrospective",
            "platform": {"days": int(net.size), "mean_annual": mean, "se_annual": se, "economic_lower_90": lower,
                         "economic_pass": econ_pass},
        }
    sigma21 = np.nan_to_num(sigma_daily[-1] * math.sqrt(21), nan=0.05)
    out = run.daily(run.CompositeInputs(as_of=as_of, asset_ids=tuple(ids), signals=tuple(inputs),
                                        sigma_residual=sigma21, frozen_weights=registry.frozen_weights() or None), cfg)
    params = load_registry()
    symbols = {i: (master.symbols(i) or [i])[-1] for i in ids}
    signals = []
    for rec in out.signals:
        ev = evidence[rec["signal_id"]]
        reasons = []
        for r in rec["reasons"]:
            label = ""
            if "[" in r and r.endswith("]"):
                path = r[r.rindex("[") + 1:-1]
                label = f" {params.label(path)}" if path in params.parameters else ""
            reasons.append(r + label)
        signals.append({**rec, "reasons": reasons, **ev,
                        "scores": {
                            "validity": _validity(registry, ev),
                            "predictive": "NOT AVAILABLE. No prospective forecast record yet",
                            "economic": _economic(ev)}})
    record = {
        "composite_run_id": out.composite_run_id, "as_of": out.as_of.isoformat(), "universe_hash": out.universe_hash,
        "config_hash": out.config_hash, "record_type": "retrospective", "data_labels": list(labels),
        "signals": signals, "unallocated_weight": out.unallocated_weight,
        "calibration_status": out.calibration_status, "calibration_reasons": list(out.calibration_reasons),
        "optimizer_status": out.optimizer_status,
        "scores": [{"symbol": symbols[i], "score": float(s)} for i, s in zip(ids, out.score)],
        "contributions": {symbols[i]: {sig["signal_id"]: float(out.contributions[k][j]) for k, sig in enumerate(signals)}
                          for j, i in enumerate(ids)},
        "benchmarks": {k: [float(v) for v in vals] for k, vals in out.benchmarks.items()},
        "frozen_weights": registry.frozen_weights(), "trial_count": registry.variant_count(),
    }
    capital = {s["signal_id"]: s["capital_weight"] for s in signals if s["capital_weight"] > 0}
    if capital:
        registry.freeze_weights(capital, ensure_utc(now))
    registry.save_run(out.composite_run_id, out.as_of, record)
    return record


def _validity(registry: ResearchRegistry, ev: dict) -> str:
    if not ev["experiments"]:
        return "NOT AVAILABLE. No published claim reproduced for this signal"
    parts = []
    for eid in ev["experiments"]:
        e = registry.experiment(eid)
        r = e["result"] or {}
        parts.append(f"{e['study_type']} {e['status']} (mean {r.get('mean_monthly_pct')}% a month, t {r.get('t_stat')})")
    return ". ".join(parts)


def _economic(ev: dict) -> str:
    p = ev["platform"]
    if p["economic_lower_90"] is None:
        return "NOT AVAILABLE. Not enough platform history"
    return (f"{p['mean_annual'] * 100:.1f}% a year net at 10% volatility, 90% lower bound "
            f"{p['economic_lower_90'] * 100:.1f}%, {', '.join(ev['data_labels'])}, {ev['record_type'].upper()}")
