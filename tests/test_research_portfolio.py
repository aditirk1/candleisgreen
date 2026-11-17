"""Spec C.3: research portfolios, vol scaling, costs and the long-only series."""
import numpy as np
import pytest

from candleisgreen.composite import research_portfolio as rp
from candleisgreen.composite.stats import annualized_mean_and_se
from candleisgreen.core.config import load_config


@pytest.fixture(scope="module")
def comp():
    return load_config().composite


def _market(T, N, rng, edge=0.0, z=None, spread=0.0005):
    z = rng.normal(size=(T, N)) if z is None else z
    returns = edge * z + rng.normal(0, 0.02, (T, N))
    return z, rp.MarketInputs(
        returns=returns, half_spread=np.full((T, N), spread), sigma_daily=np.full((T, N), 0.02),
        adv_usd=np.full((T, N), 5e7), price=np.full((T, N), 50.0),
    )


def test_weights_use_no_future_returns(comp):
    rng = np.random.default_rng(30)
    z, market = _market(300, 50, rng)
    base = rp.build(z, "cross_sectional", market, comp)
    changed = market.returns.copy()
    changed[150:] *= 10
    shifted = rp.build(z, "cross_sectional", rp.MarketInputs(changed, market.half_spread, market.sigma_daily,
                                                             market.adv_usd, market.price), comp)
    assert np.array_equal(base.weights[:151], shifted.weights[:151])


def test_cross_sectional_is_dollar_neutral_and_hits_the_vol_target(comp):
    rng = np.random.default_rng(31)
    z, market = _market(2000, 100, rng)
    out = rp.build(z, "cross_sectional", market, comp)
    live = out.active
    assert np.abs(out.weights[live].sum(axis=1)).max() < 1e-12
    realized = out.gross[live].std(ddof=1) * np.sqrt(252)
    assert realized == pytest.approx(comp.research_portfolio.vol_target_annual, abs=0.015)


def test_planted_edge_is_recovered(comp):
    """A known edge comes back inside three standard errors, and noise comes back near zero."""
    rng = np.random.default_rng(32)
    T, N, c, s = 3000, 200, 0.0001, 0.02
    z, market = _market(T, N, rng, edge=c)
    out = rp.build(z, "cross_sectional", market, comp)
    # Daily Sharpe of a dollar-neutral portfolio proportional to z: c sqrt(N) / sqrt(2c^2 + s^2).
    true_annual = 0.10 * c * np.sqrt(N) / np.sqrt(2 * c * c + s * s) * np.sqrt(252)
    mean, se, _ = annualized_mean_and_se(out.gross[out.active], 1, 63, 252)
    assert abs(mean - true_annual) < 3 * se
    z0, noise = _market(T, N, np.random.default_rng(33))
    out0 = rp.build(z0, "cross_sectional", noise, comp)
    mean0, se0, _ = annualized_mean_and_se(out0.gross[out0.active], 1, 63, 252)
    assert abs(mean0) < 3 * se0


def test_costs_are_charged_and_grow_with_the_spread(comp):
    rng = np.random.default_rng(34)
    z, market = _market(300, 50, rng)
    cheap = rp.build(z, "cross_sectional", market, comp)
    _, wide_market = _market(300, 50, np.random.default_rng(34), spread=0.005)
    wide = rp.build(z, "cross_sectional", wide_market, comp)
    assert (cheap.cost >= 0).all() and np.allclose(cheap.net, cheap.gross - cheap.cost)
    assert wide.cost.sum() > 5 * cheap.cost.sum()


def test_borrow_is_charged_only_on_short_legs(comp):
    rng = np.random.default_rng(35)
    z, market = _market(300, 50, rng, spread=0.0)
    no_trade_cost = rp.MarketInputs(market.returns, market.half_spread, np.zeros_like(market.sigma_daily),
                                    market.adv_usd, market.price)
    xs = rp.build(z, "cross_sectional", no_trade_cost, comp)
    shorts = np.clip(-xs.weights, 0, None).sum(axis=1)
    sells = np.clip(-np.diff(np.vstack([np.zeros(50), xs.weights]), axis=0), 0, None).sum(axis=1)
    fees = sells * comp.research_portfolio.research_nav_usd * comp.costs.sec_fee_per_million_usd_sold / 1e6
    expected = shorts * comp.costs.borrow_rate_annual / 252 + fees / comp.research_portfolio.research_nav_usd
    assert xs.cost == pytest.approx(expected, rel=1e-9, abs=1e-15)
    ts = rp.build(np.abs(z), "time_series", no_trade_cost, comp)
    assert (ts.weights >= 0).all()


def test_long_only_series_and_vol_scale(comp):
    rng = np.random.default_rng(36)
    z, market = _market(1500, 90, rng, edge=0.0002)
    out = rp.build(z, "cross_sectional", market, comp)
    gross = out.long_only_net + out.long_only_cost
    assert gross[out.active].mean() > 0  # the top third beats the universe before costs
    # z is redrawn every day, so the book turns over almost fully and costs swamp the edge.
    assert out.long_only_cost[out.active].mean() > gross[out.active].mean()
    assert (out.long_only_cost >= 0).all()
    assert out.vol_scale > 0 and np.isfinite(out.vol_scale)


def test_no_weights_before_enough_history(comp):
    rng = np.random.default_rng(37)
    z, market = _market(100, 20, rng)
    out = rp.build(z, "cross_sectional", market, comp)
    assert not out.active[: comp.costs.min_vol_history_days].any()
    assert np.abs(out.weights[: comp.costs.min_vol_history_days]).sum() == 0


def test_builder_output_feeds_the_daily_composite_run():
    from datetime import datetime, timezone

    from candleisgreen.composite import run
    from candleisgreen.composite.eligibility import SignalState, economic_test

    cfg = load_config()
    comp = cfg.composite
    rng = np.random.default_rng(38)
    # About 10 years and annual Sharpe near 1.8 for the real signals, so the standard error
    # of each estimate (about 3%) is well below the planted edges.
    T, N = 2500, 60
    signals = []
    for sid, family, edge in (("mom", "momentum", 0.0003), ("val", "value", 0.0003), ("noise", "quality", 0.0)):
        z = rng.normal(size=(T, N))
        z = np.cumsum(z, axis=0) / np.sqrt(np.arange(1, T + 1))[:, None]  # persistent scores, low turnover
        _, market = _market(T, N, rng, edge=edge, z=z)
        series = rp.build(z, "cross_sectional", market, comp)
        net = series.net[series.active]
        mean, se, _ = annualized_mean_and_se(net, 21, comp.research_portfolio.newey_west_max_lag_days, 252)
        elig = comp.eligibility.model_copy(update={"bootstrap_resamples": 300})
        _, passed = economic_test(net, series.cost[series.active], elig, rng)
        state = SignalState(sid, family, "cross_sectional", 21, 5 if passed else 3, int(net.size),
                            vol_scale=series.vol_scale)
        signals.append(run.SignalInput(state, z[-1], net, mean, se,
                                       datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)))
    out = run.daily(run.CompositeInputs(datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc),
                                        tuple(f"a{i}" for i in range(N)), tuple(signals), np.full(N, 0.06)), cfg)
    by_id = {s["signal_id"]: s for s in out.signals}
    assert by_id["mom"]["eligible"] and by_id["val"]["eligible"]
    assert not by_id["noise"]["eligible"]
    assert by_id["mom"]["capital_weight"] > 0 and by_id["noise"]["capital_weight"] == 0
    assert out.score.shape == (N,) and out.score.std() == pytest.approx(1.0)
    assert out.calibration_status == "signal_strength_only"  # no calibration history was given
