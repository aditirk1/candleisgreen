"""Spec v3.2 Q6, Q8 and Q14."""
import numpy as np
import pytest

from candleisgreen.composite import edge, monitoring
from candleisgreen.composite.eligibility import ShadowRecord, StrategyPromotionPolicy, promotion_check
from candleisgreen.core.config import load_config

DAILY_VOL = 0.10 / np.sqrt(252)


@pytest.fixture(scope="module")
def comp():
    return load_config().composite


# Q6 --------------------------------------------------------------------------------------

def test_infrastructure_failures_pause_without_statistics():
    assert monitoring.infrastructure_check(True, True, True).paused is False
    assert monitoring.infrastructure_check(False, True, True).paused
    assert monitoring.infrastructure_check(True, None, True).reasons == ("price validity unknown",)


def test_strategy_performing_as_forecast_alerts_at_about_the_stated_rate(comp):
    rng = np.random.default_rng(50)
    mu, var = 0.05, 0.02**2
    alerts = 0
    for _ in range(2000):
        true_mu = rng.normal(mu, np.sqrt(var))  # truth drawn from the forecast distribution
        daily = rng.normal(true_mu / 252, DAILY_VOL, 252)
        alerts += monitoring.deterioration_test(daily, mu, var, 1, comp.monitoring).status == "alert"
    assert 0.03 <= alerts / 2000 <= 0.07


def test_dead_strategy_alerts_more_with_more_evidence(comp):
    rng = np.random.default_rng(51)
    rates = []
    # Forecast 8% a year, truth -5%. The gap is about 1.5 sampling SDs at 126 days and 3 at 1500.
    for days in (126, 1500):
        cfg = comp.monitoring.model_copy(update={"review_window_days": days})
        hits = sum(
            monitoring.deterioration_test(rng.normal(-0.05 / 252, DAILY_VOL, days), 0.08, 0.01**2, 1, cfg).status
            == "alert" for _ in range(400)
        )
        rates.append(hits / 400)
    assert rates[1] > rates[0] and rates[1] > 0.8


def test_short_records_are_not_judged(comp):
    res = monitoring.deterioration_test(np.full(20, -0.01), 0.05, 0.0004, 1, comp.monitoring)
    assert res.status == "insufficient_data" and res.probability is None


def test_edge_uncertainty_widens_the_forecast_distribution(comp):
    rng = np.random.default_rng(52)
    daily = rng.normal(0.0, DAILY_VOL, 252)
    daily = daily - daily.mean() - 0.04 / 252  # realized -4% against a 6% forecast
    tight = monitoring.deterioration_test(daily, 0.06, 0.0001, 1, comp.monitoring)
    loose = monitoring.deterioration_test(daily, 0.06, 0.0025, 1, comp.monitoring)
    assert loose.predictive_sd_annual > tight.predictive_sd_annual
    assert loose.probability > tight.probability


# Q8 --------------------------------------------------------------------------------------

def _shadow(**kw):
    base = dict(trading_days=63, trades=25, expected_mean_annual=0.06, realized_mean_annual=0.05,
                realized_se_annual=0.05, band_low_annual=-0.10, band_high_annual=0.20, tracking_error_annual=0.03)
    base.update(kw)
    return ShadowRecord(**base)


def test_promotion_needs_days_trades_precision_band_and_tracking(comp):
    cfg = comp.promotion
    assert promotion_check(_shadow(), cfg).eligible
    assert not promotion_check(_shadow(trading_days=62), cfg).eligible
    assert not promotion_check(_shadow(trades=5), cfg).eligible
    assert not promotion_check(_shadow(realized_se_annual=0.08), cfg).eligible
    assert not promotion_check(_shadow(realized_mean_annual=0.30), cfg).eligible
    assert not promotion_check(_shadow(tracking_error_annual=0.06), cfg).eligible
    assert not promotion_check(_shadow(prospective=False), cfg).eligible


def test_strategy_declares_its_own_trade_and_precision_needs(comp):
    cfg = comp.promotion
    slow = StrategyPromotionPolicy(min_trades=6)
    assert promotion_check(_shadow(trades=8), cfg, slow).eligible
    strict = StrategyPromotionPolicy(max_se_to_expected_ratio=0.5)
    assert not promotion_check(_shadow(), cfg, strict).eligible
    assert not promotion_check(_shadow(trading_days=40), cfg, slow).eligible  # 63 days stays the minimum


# Q14 -------------------------------------------------------------------------------------

def test_academic_evidence_supports_but_never_dominates(comp):
    ev = edge.academic_evidence(0.06, 0.01, 0.01, comp.edge)
    assert ev.kind == "academic_oos" and ev.value == pytest.approx(0.05)
    assert ev.variance == pytest.approx(0.01**2 + (0.5 * 0.06) ** 2)
    alone = edge.estimate([ev])
    assert alone.prob_positive < 0.96  # the implementation gap caps confidence


def test_academic_evidence_cannot_grant_capital_without_prospective_tier():
    from datetime import datetime, timezone

    from candleisgreen.composite import run
    from candleisgreen.composite.eligibility import SignalState

    cfg = load_config()
    rng = np.random.default_rng(53)
    returns = rng.normal(0.0002, DAILY_VOL, 600)
    state = SignalState("mom", "momentum", "cross_sectional", 21, 4, 600)
    sig = run.SignalInput(state, rng.normal(size=20), returns, returns.mean() * 252,
                          returns.std(ddof=1) * np.sqrt(252 / 600),
                          datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc),
                          academic=run.AcademicRecord(0.08, 0.01, 0.01, "cc_by_4_0"))
    out = run.daily(run.CompositeInputs(datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc),
                                        tuple(f"a{i}" for i in range(20)), (sig,), np.full(20, 0.06)), cfg)
    rec = out.signals[0]
    assert rec["capital_weight"] == 0.0  # Tier 4 is shadow only, capital needs the Tier 5 prospective record
