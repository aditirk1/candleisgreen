"""Spec section C, one step at a time."""
import math

import numpy as np
import pytest

from candleisgreen.composite import combine, edge, standardize, weights
from candleisgreen.composite.eligibility import SignalState, is_eligible


@pytest.fixture(scope="module")
def comp():
    from candleisgreen.core.config import load_config

    return load_config().composite


# C.4 -------------------------------------------------------------------------------------

def test_worked_example_c11(comp):
    paper = edge.paper_evidence(0.08, 0.02, edge.delta_for("us_published", comp.edge), 0.01, comp.edge)
    est = edge.estimate([paper, edge.oos_evidence(0.05, 0.025), edge.family_prior([], [], comp.edge)])
    assert paper.value == pytest.approx(0.0236)
    assert paper.variance == pytest.approx(0.000353, rel=1e-3)
    assert est.mu_hat == pytest.approx(0.0304, abs=5e-5)
    assert est.std == pytest.approx(0.0144, abs=5e-5)
    assert est.prob_positive == pytest.approx(0.98, abs=0.005)


def test_noise_example_c11(comp):
    est = edge.estimate([edge.oos_evidence(0.005, 0.025), edge.family_prior([], [], comp.edge)])
    assert est.mu_hat == pytest.approx(0.0040, abs=1e-5)
    assert est.prob_positive == pytest.approx(0.57, abs=0.005)


def test_delta_cancels_for_paper_only_evidence(comp):
    """REVIEW E3: with paper alone, P depends on the paper's t only."""
    probs = []
    for delta in (0.42, 0.74, 1.0):
        probs.append(edge.estimate([edge.paper_evidence(0.08, 0.02, delta, 0.0, comp.edge)]).prob_positive)
    assert max(probs) - min(probs) < 1e-12
    huge_t = edge.estimate([edge.paper_evidence(0.08, 0.0001, 0.42, 0.0, comp.edge)]).prob_positive
    assert huge_t < 0.978


def test_no_paper_measurement_for_discoveries_and_practitioners(comp):
    assert edge.delta_for("platform_discovery", comp.edge) is None
    assert edge.delta_for("practitioner", comp.edge) is None
    with pytest.raises(ValueError):
        edge.delta_for("unknown", comp.edge)


def test_family_prior_cold_start_and_floor(comp):
    cold = edge.family_prior([0.02, 0.03], [0.02, 0.02], comp.edge)
    assert (cold.value, cold.variance) == (0.0, pytest.approx(0.05**2))
    tight = edge.family_prior([0.02] * 5, [0.03] * 5, comp.edge)
    assert tight.variance == pytest.approx(comp.edge.tau_floor_annual**2)


def test_family_delta_needs_enough_signals(comp):
    assert edge.family_delta([0.01] * 19, [0.02] * 19, comp.edge) is None
    assert edge.family_delta([0.01] * 20, [0.02] * 20, comp.edge) == pytest.approx(0.5)


def test_evidence_must_have_positive_variance():
    with pytest.raises(ValueError):
        edge.Evidence("out_of_sample", 0.01, 0.0)


# C.5 -------------------------------------------------------------------------------------

def _state(**kw):
    base = dict(signal_id="s", family="trend", signal_type="cross_sectional", horizon_days=21, tier=4, oos_days=300)
    base.update(kw)
    return SignalState(**base)


def test_eligibility_rules(comp):
    good = edge.EdgeEstimate(0.03, 0.0001, 0.99, ("out_of_sample",))
    cfg = comp.eligibility
    assert is_eligible(_state(), good, cfg).eligible
    assert not is_eligible(_state(), good, cfg).capital
    assert is_eligible(_state(tier=5), good, cfg).capital
    assert not is_eligible(_state(tier=3), good, cfg).eligible
    assert not is_eligible(_state(oos_days=251), good, cfg).eligible
    assert not is_eligible(_state(feed_healthy=False), good, cfg).eligible
    assert not is_eligible(_state(data_labels=("SURVIVORSHIP-BIASED",)), good, cfg).eligible
    weak = edge.EdgeEstimate(0.01, 0.0001, 0.79, ("out_of_sample",))
    assert not is_eligible(_state(), weak, cfg).eligible
    event = _state(signal_type="event", oos_days=40, oos_events=30)
    assert is_eligible(event, good, cfg).eligible
    assert not is_eligible(_state(signal_type="event", oos_days=40, oos_events=29), good, cfg).eligible


# C.2 -------------------------------------------------------------------------------------

def test_cross_sectional_zscore(comp):
    rng = np.random.default_rng(1)
    raw = rng.normal(size=500)
    raw[0], raw[1] = 1e6, np.nan
    z = standardize.cross_sectional(raw, comp.standardize)
    assert z[1] == 0.0  # missing means no view
    assert abs(z[2:].mean()) < 0.05 and abs(z[np.arange(500) != 1].std() - 1) < 0.05
    assert z[0] < 4  # the outlier was winsorized


def test_sector_neutral_zscore(comp):
    """Winsorize across the universe, then z-score within each sector."""
    rng = np.random.default_rng(8)
    raw = np.concatenate([rng.normal(0, 1, 200), rng.normal(100, 5, 200)])
    sectors = np.array(["a"] * 200 + ["b"] * 200)
    z = standardize.cross_sectional(raw, comp.standardize, sectors)
    for name in "ab":
        part = z[sectors == name]
        assert abs(part.mean()) < 1e-9 and part.std() == pytest.approx(1.0)


def test_time_series_uses_only_past_and_is_clipped(comp):
    rng = np.random.default_rng(2)
    raw = rng.normal(size=(300, 3))
    z = standardize.time_series(raw, comp.standardize)
    changed = raw.copy()
    changed[200:] *= 50  # future values must not change earlier rows
    z2 = standardize.time_series(changed, comp.standardize)
    assert np.array_equal(z[:200], z2[:200])
    assert np.abs(z).max() <= comp.standardize.ts_clip


def test_smoothing_half_life(comp):
    step = np.zeros((200, 1))
    step[50:] = 1.0
    out = standardize.smooth(step, 20, "time_series", comp.standardize)  # half-life 10 days
    assert out[60, 0] == pytest.approx(0.5, abs=0.04)


def test_event_signals_are_not_smoothed_out_of_their_window(comp):
    z = np.zeros((30, 2))
    z[10:13, 0] = 1.5
    window = np.zeros((30, 2), dtype=bool)
    window[10:13, 0] = True
    out = standardize.apply_event_window(standardize.smooth(z, 20, "event", comp.standardize), window)
    assert out[13:].sum() == 0 and out[:10].sum() == 0


def test_practitioner_claim_decays_linearly():
    assert standardize.practitioner_claim(1, 0.8, 0, 10) == pytest.approx(0.8)
    assert standardize.practitioner_claim(-1, 1.0, 5, 10) == pytest.approx(-0.5)
    assert standardize.practitioner_claim(1, 1.0, 10, 10) == 0.0


# C.6 -------------------------------------------------------------------------------------

def test_caps_with_three_signals_leave_forty_percent_unallocated(comp):
    """C.12: with three signals the caps leave 40% unallocated and the step ends."""
    w, unallocated = weights.apply_caps(np.array([0.5, 0.3, 0.2]), ["a", "b", "c"], comp.weights)
    assert w == pytest.approx([0.2, 0.2, 0.2])
    assert unallocated == pytest.approx(0.4)


def test_caps_redistribute_and_respect_family_cap(comp):
    raw = np.array([0.30, 0.25, 0.15, 0.10, 0.10, 0.10])
    fams = ["a", "a", "b", "b", "c", "c"]
    w, unallocated = weights.apply_caps(raw, fams, comp.weights)
    assert w.max() <= 0.2 + 1e-9
    for fam in "abc":
        assert w[[f == fam for f in fams]].sum() <= 0.35 + 1e-9
    assert w.sum() + unallocated == pytest.approx(1.0)


def test_change_limit(comp):
    cfg = comp.weights
    prev = np.array([0.20, 0.01, 0.0, 0.10])
    new = np.array([0.10, 0.10, 0.20, 0.0])
    out = weights.limit_change(new, prev, cfg, removed=np.array([False, False, False, True]))
    assert out[0] == pytest.approx(0.15)  # 25% of 0.20
    assert out[1] == pytest.approx(0.03)  # 2 point floor
    assert out[2] == pytest.approx(0.05)  # new entry cap
    assert out[3] == 0.0  # removal is immediate


def test_within_family_is_nonnegative_and_sums_to_one(comp):
    rng = np.random.default_rng(3)
    returns = rng.normal(0, 0.006, size=(600, 4))
    w = weights.within_family(np.array([0.03, -0.01, 0.02, 0.01]), returns, comp.weights)
    assert (w >= 0).all() and w.sum() == pytest.approx(1.0)
    assert w[1] == pytest.approx(0.0, abs=1e-9)


def test_hrp_gives_less_weight_to_riskier_families():
    rng = np.random.default_rng(4)
    r = rng.normal(0, 1, size=(800, 3)) * np.array([0.005, 0.01, 0.02])
    w = weights.hierarchical_risk_parity(r)
    assert w.sum() == pytest.approx(1.0) and w[0] > w[1] > w[2]


# C.7 -------------------------------------------------------------------------------------

def test_score_is_demeaned_and_unit_scale():
    rng = np.random.default_rng(5)
    z = rng.normal(size=(3, 400)) + 2.0
    s = combine.composite_score(z, np.array([0.2, 0.2, 0.2]), np.array([1.0, 2.0, 1.0]))
    assert abs(s.mean()) < 1e-12 and s.std() == pytest.approx(1.0)


def test_vol_scale_changes_the_mix():
    z = np.array([[1.0, -1.0, 0.0], [0.0, 1.0, -1.0]])
    same = combine.composite_score(z, np.array([0.5, 0.5]), np.array([1.0, 1.0]))
    scaled = combine.composite_score(z, np.array([0.5, 0.5]), np.array([1.0, 3.0]))
    assert not np.allclose(same, scaled)


def test_alpha_shrinkage_clip_and_allocation(comp):
    cfg = comp.alpha
    s = np.array([5.0, 1.0, -1.0])
    a = combine.alpha(s, np.full(3, 0.1), 0.05, 252, 0.6, cfg)
    assert a[1] == pytest.approx(0.05 * 0.5 * 0.1 * 1.0 * 0.6)
    assert a[0] == pytest.approx(3 * a[1])


def test_calibration_uses_the_unshrunk_forecast(comp):
    """REVIEW E12: a well-specified model calibrates at n = 252, the shrunk alpha would not."""
    cfg = comp.alpha
    rng = np.random.default_rng(6)
    forecast = rng.normal(0, 0.01, 20000)
    realized = forecast + rng.normal(0, 0.03, 20000)
    daily_ic = rng.normal(0.05, 0.05, 252)
    good = combine.calibration(realized, forecast, daily_ic, cfg)
    assert good.calibrated and good.slope == pytest.approx(1.0, abs=0.1)
    shrunk = forecast * 252 / (252 + cfg.ic_shrink_days)
    assert not combine.calibration(realized, shrunk, daily_ic, cfg).calibrated


def test_ic_t_statistic_accounts_for_overlap(comp):
    rng = np.random.default_rng(7)
    noise = np.convolve(rng.normal(0, 0.1, 2000), np.ones(21) / 21, mode="valid")  # overlapping, zero mean
    naive_t = noise.mean() / (noise.std(ddof=1) / math.sqrt(noise.size))
    _, nw_t = combine.ic_statistics(noise, comp.alpha)
    assert abs(nw_t) < abs(naive_t) / 2
