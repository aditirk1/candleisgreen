"""Spec C.12 required tests for the Composite."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from candleisgreen.composite import edge, optimizer, riskmodel, run, weights
from candleisgreen.composite.eligibility import SignalState, economic_test, is_eligible, replication_test
from candleisgreen.core.config import load_config
from candleisgreen.data.pit_store import LookaheadError
from candleisgreen.risk.engine import evaluate_portfolio

AS_OF = datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc)
DAILY_VOL = 0.10 / np.sqrt(252)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# 1. Known true edges are recovered within their stated intervals at the stated rate ----------

def test_intervals_cover_true_edges_at_the_stated_rate(cfg):
    rng = np.random.default_rng(10)
    tau = cfg.composite.edge.cold_start_tau_annual
    runs, hits = 4000, 0
    for _ in range(runs):
        true_mu = rng.normal(0.0, tau)  # true edges drawn from the stated prior
        se_oos = rng.uniform(0.015, 0.06)
        se_paper = rng.uniform(0.02, 0.05)
        evidence = [
            edge.family_prior([], [], cfg.composite.edge),
            edge.oos_evidence(true_mu + rng.normal(0, se_oos), se_oos),
            edge.Evidence("paper", true_mu + rng.normal(0, se_paper), se_paper**2),
        ]
        lo, hi = edge.estimate(evidence).interval(1.6449)  # 90% interval
        hits += lo <= true_mu <= hi
    assert 0.88 <= hits / runs <= 0.92


# 2. Pure-noise signals are excluded in at least 95% of simulated runs -----------------------

def test_pure_noise_is_excluded_by_the_joint_gate(cfg):
    """A zero-edge signal walks the real path: Tier 3 replication on independent data,
    then the Tier 4 economic test after its cutoff, then the P_s gate."""
    elig = cfg.composite.eligibility.model_copy(update={"bootstrap_resamples": 300})
    rp = cfg.composite.research_portfolio
    rng = np.random.default_rng(11)
    runs, admitted = 600, 0
    for i in range(runs):
        replication = rng.normal(0.0, DAILY_VOL, int(rng.integers(252, 1500)))
        _, tier3 = replication_test(replication, 21, rp.newey_west_max_lag_days, elig)
        days = int(rng.integers(252, 1500))
        daily = rng.normal(0.0, DAILY_VOL, days)  # zero true edge, 10% volatility
        _, tier4 = economic_test(daily, np.full(days, 0.00002), elig, rng)
        mean = daily.mean() * rp.trading_days_per_year
        se = daily.std(ddof=1) * np.sqrt(rp.trading_days_per_year / days)
        est = edge.estimate([edge.family_prior([], [], cfg.composite.edge), edge.oos_evidence(mean, se)])
        tier = 4 if (tier3 and tier4) else (3 if tier3 else 2)
        state = SignalState(f"noise{i}", "trend", "time_series", 21, tier, days)
        admitted += is_eligible(state, est, elig).eligible
    assert (runs - admitted) / runs >= 0.95


def test_tier4_alone_admits_noise_at_its_nominal_rate(cfg):
    """REVIEW E30: the Tier 4 test alone lets through about 5% of noise, so it gives no
    margin over the 95% bar on its own. This pins that property."""
    elig = cfg.composite.eligibility.model_copy(update={"bootstrap_resamples": 300})
    rng = np.random.default_rng(21)
    runs = 1500
    passed = sum(
        economic_test(rng.normal(0.0, DAILY_VOL, n), np.zeros(n), elig, rng)[1]
        for n in rng.integers(252, 1500, runs)
    )
    assert 0.03 <= passed / runs <= 0.08


def test_a_real_edge_usually_passes_the_economic_test(cfg):
    elig = cfg.composite.eligibility.model_copy(update={"bootstrap_resamples": 300})
    rng = np.random.default_rng(12)
    daily = rng.normal(0.08 / 252, DAILY_VOL, 2500)  # Sharpe 0.8 over ten years
    lower, passed = economic_test(daily, np.full(2500, 0.00001), elig, rng)
    assert passed and lower > 0


# 3. Two identical copies get the same total weight as one copy ------------------------------

def test_identical_copies_share_one_budget(cfg):
    wcfg = cfg.composite.weights
    rng = np.random.default_rng(13)
    base = rng.normal(0, DAILY_VOL, size=(800, 4))
    mu = np.array([0.03, 0.02, 0.025, 0.015])
    fams = ["trend", "trend", "value", "reversal"]
    one = weights.signal_weights(mu, base, fams, wcfg)
    two = weights.signal_weights(
        np.append(mu, mu[0]), np.column_stack([base, base[:, 0]]), fams + ["trend"], wcfg
    )
    assert two.pre_cap[[0, 4]].sum() == pytest.approx(one.pre_cap[0], abs=0.02)
    assert two.pre_cap[1:4] == pytest.approx(one.pre_cap[1:4], abs=0.02)


# 4. An input first usable after decision time fails the build -------------------------------

def _signal(sid, family, tier, mu_daily, rng, n_assets, usable=AS_OF - timedelta(hours=1), days=600):
    returns = rng.normal(mu_daily, DAILY_VOL, days)
    mean = returns.mean() * 252
    se = returns.std(ddof=1) * np.sqrt(252 / days)
    state = SignalState(sid, family, "cross_sectional", 21, tier, days)
    return run.SignalInput(state, rng.normal(size=n_assets), returns, mean, se, usable)


def test_input_usable_after_decision_time_fails(cfg):
    rng = np.random.default_rng(14)
    late = _signal("late", "trend", 5, 0.0004, rng, 10, usable=AS_OF)
    inputs = run.CompositeInputs(AS_OF, tuple(f"a{i}" for i in range(10)), (late,), np.full(10, 0.05))
    with pytest.raises(LookaheadError, match="late"):
        run.daily(inputs, cfg)


# Shared synthetic book --------------------------------------------------------------------

N = 40


def _book(cfg, rng, x0=None):
    market = rng.normal(0, 0.01, (300, 1))
    daily = market * rng.uniform(0.5, 1.5, N) + rng.normal(0, 0.015, (300, N))
    model = riskmodel.fit(daily, cfg.composite.optimizer)
    return run.BookInputs(
        model=model, x0=np.zeros(N) if x0 is None else x0, half_spread=np.full(N, 0.0005),
        sigma_daily=daily.std(axis=0), adv_usd=np.full(N, 5e7), nav_usd=1e5,
        sectors=tuple(f"sec{i % 6}" for i in range(N)), clusters=tuple(f"cl{i % 8}" for i in range(N)),
    )


def _calibration(good: bool, rng):
    forecast = rng.normal(0, 0.01, 5000)
    realized = (forecast if good else -forecast) + rng.normal(0, 0.03, 5000)
    ic = rng.normal(0.05 if good else -0.01, 0.05, 504)
    return run.CalibrationInputs(realized, forecast, ic, 504)


def _inputs(cfg, rng, good_calibration=True, x0=None, prev=None, frozen=None):
    signals = (
        _signal("mom", "momentum", 5, 0.0006, rng, N),
        _signal("rev", "reversal", 5, 0.0005, rng, N),
        _signal("val", "value", 4, 0.0005, rng, N),
        _signal("noise", "quality", 5, 0.0, rng, N),
    )
    return run.CompositeInputs(
        AS_OF, tuple(f"a{i}" for i in range(N)), signals, np.full(N, 0.06),
        calibration=_calibration(good_calibration, rng), book=_book(cfg, rng, x0),
        prev_weights=prev, frozen_weights=frozen,
    )


def test_daily_run_writes_the_output_contract(cfg):
    out = run.daily(_inputs(cfg, np.random.default_rng(15), frozen={"mom": 0.1, "rev": 0.1}), cfg)
    assert out.composite_run_id.startswith("crun_") and out.universe_hash.startswith("univ_")
    by_id = {s["signal_id"]: s for s in out.signals}
    assert by_id["val"]["eligible"] and by_id["val"]["capital_weight"] == 0.0  # Tier 4 is shadow only
    assert out.calibration_status == "calibrated" and out.alpha is not None
    assert out.optimizer_status in ("optimal", "vol_below_target")
    assert out.ex_ante_vol_annual <= cfg.composite.optimizer.vol_target_annual + 1e-6
    assert 0.0 <= out.unallocated_weight < 1.0
    assert out.contributions.shape == (4, N)
    again = run.daily(_inputs(cfg, np.random.default_rng(15), frozen={"mom": 0.1, "rev": 0.1}), cfg)
    assert again.composite_run_id == out.composite_run_id


# 5. A failed calibration blocks new positions ---------------------------------------------

def test_failed_calibration_blocks_new_positions(cfg):
    rng = np.random.default_rng(16)
    x0 = np.zeros(N)
    x0[:5] = 0.04
    out = run.daily(_inputs(cfg, rng, good_calibration=False, x0=x0), cfg)
    assert out.calibration_status == "signal_strength_only" and out.alpha is None
    assert out.calibration_reasons
    assert out.optimizer_status == "reduce_only"
    assert (out.target_weights <= x0 + 1e-9).all()
    assert out.target_weights[5:].sum() == pytest.approx(0.0, abs=1e-9)


# 6. The optimizer never breaks a hard limit, and the risk check rejects an injected book ----

@pytest.mark.parametrize("seed", range(6))
def test_optimizer_respects_every_hard_limit(cfg, seed):
    rng = np.random.default_rng(100 + seed)
    book = _book(cfg, rng)
    alpha = rng.normal(0, 0.01, N)
    alpha[:3] = 0.5  # huge alpha on a few names tries to force concentration
    adv = np.full(N, 5e7)
    adv[:2] = 2e5  # tiny ADV makes the order-size limit bind
    inputs = optimizer.OptimizerInputs(alpha, book.model, book.x0, book.half_spread, book.sigma_daily, adv,
                                       book.nav_usd, book.sectors, book.clusters)
    limits = cfg.risk.hard_limits
    res = optimizer.solve(inputs, limits, cfg.composite.optimizer)
    assert res.status != "failed"
    assert optimizer.violations(res.weights, inputs, limits, cfg.composite.optimizer) == []
    clusters = {f"a{i}": c for i, c in enumerate(book.clusters)}
    assert evaluate_portfolio({f"a{i}": w for i, w in enumerate(res.weights)}, clusters, limits) == ()
    assert res.weights[:2].max() <= limits.max_order_pct_adv20 * 2e5 / 1e5 + 1e-9


def test_risk_check_rejects_an_injected_book(cfg):
    limits = cfg.risk.hard_limits
    clusters = {"a": "c1", "b": "c1", "c": "c2", "d": "c1", "e": "c1", "f": "c1"}
    assert evaluate_portfolio({"a": 0.08}, clusters, limits)  # position over 5%
    assert evaluate_portfolio({k: 0.045 for k in "abdef"}, clusters, limits)  # cluster at 22.5%
    assert evaluate_portfolio({"a": -0.01}, clusters, limits)  # short
    assert evaluate_portfolio({"zzz": 0.01}, clusters, limits)  # no cluster mapping
    assert evaluate_portfolio({"a": float("nan")}, clusters, limits)
    assert evaluate_portfolio({"a": 0.04, "c": 0.04}, clusters, limits) == ()


def test_volatility_target_is_an_upper_bound(cfg):
    rng = np.random.default_rng(17)
    book = _book(cfg, rng)
    inputs = optimizer.OptimizerInputs(np.full(N, 0.05), book.model, book.x0, book.half_spread, book.sigma_daily,
                                       book.adv_usd, book.nav_usd, book.sectors, book.clusters)
    low_target = cfg.composite.optimizer.model_copy(update={"vol_target_annual": 0.03})
    res = optimizer.solve(inputs, cfg.risk.hard_limits, low_target)
    assert res.ex_ante_vol_annual <= 0.03 + 1e-6


# 7. Frozen-weight and champion-challenger benchmarks run every day ------------------------

def test_benchmarks_run_beside_the_live_composite(cfg):
    out = run.daily(_inputs(cfg, np.random.default_rng(18), frozen={"mom": 0.15, "rev": 0.05}), cfg)
    assert set(out.benchmarks) == {"challenger_equal_weight", "frozen_weight"}
    for series in out.benchmarks.values():
        assert series.shape == (N,) and np.isfinite(series).all() and series.std() > 0


def test_no_capital_signals_means_no_alpha(cfg):
    rng = np.random.default_rng(19)
    inputs = _inputs(cfg, rng)
    shadow_only = tuple(replace(s, state=replace(s.state, tier=4)) for s in inputs.signals)
    out = run.daily(replace(inputs, signals=shadow_only), cfg)
    assert out.unallocated_weight == pytest.approx(1.0)
    assert out.alpha is None and out.optimizer_status == "reduce_only"
