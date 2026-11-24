"""Phase 5: decision criteria by study type."""
import numpy as np
import pytest

from candleisgreen.core.config import load_config
from candleisgreen.research import criteria


@pytest.fixture(scope="module")
def cfg():
    return load_config().research.criteria


def test_benjamini_yekutieli_is_stricter_than_bh():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    by = criteria.benjamini_yekutieli(p, 0.05)
    # BY thresholds are 0.05 i / (10 x 2.929): 0.0017, 0.0034, ... so only the first is rejected.
    # Benjamini-Hochberg (0.005 i) would reject the first two.
    assert by == [True] + [False] * 9


def test_by_controls_false_discoveries_on_noise():
    rng = np.random.default_rng(70)
    false = sum(sum(criteria.benjamini_yekutieli(rng.uniform(size=50), 0.05)) for _ in range(300))
    assert false / 300 < 0.05


def test_new_factor_needs_all_three(cfg):
    noise = list(np.random.default_rng(71).uniform(size=40))
    assert criteria.new_factor_passes(4.5, 1e-5, noise, True, cfg)["passed"]
    assert not criteria.new_factor_passes(2.8, 0.005, noise, True, cfg)["passed"]  # t below 3
    assert not criteria.new_factor_passes(4.5, 1e-5, noise, False, cfg)["passed"]  # failed holdout
    many = [0.0001] * 0 + list(np.random.default_rng(72).uniform(0, 0.02, size=2000))
    out = criteria.new_factor_passes(3.2, 0.0014, many, True, cfg)
    assert out["trials"] == 2001


def test_forecast_rule_uses_clark_west_when_nested(cfg):
    rng = np.random.default_rng(73)
    x = rng.normal(size=600)
    y = 0.3 * x + rng.normal(size=600)
    good = criteria.forecast_beats_baseline(y, np.zeros(600), 0.3 * x, 1, nested=True, cfg=cfg)
    assert good["passed"] and good["test"].startswith("Clark-West")
    useless = criteria.forecast_beats_baseline(y, np.zeros(600), rng.normal(size=600) * 0.3, 1, nested=False, cfg=cfg)
    assert not useless["passed"] and useless["test"].startswith("Diebold-Mariano")


def test_forecast_rule_requires_subperiod_stability(cfg):
    rng = np.random.default_rng(74)
    x = rng.normal(size=900)
    beta = np.r_[np.full(300, 0.8), np.zeros(600)]  # works in the first third only
    y = beta * x + rng.normal(size=900)
    out = criteria.forecast_beats_baseline(y, np.zeros(900), 0.8 * x, 1, nested=True, cfg=cfg)
    assert out["subperiods_held"] < 2 and not out["passed"]


def test_event_study_with_clustered_errors(cfg):
    rng = np.random.default_rng(75)
    dates = np.repeat(np.arange(40), 10)
    shock = rng.normal(0, 0.02, 40)[dates]  # events on one date share a shock
    real = criteria.event_study(0.01 + shock + rng.normal(0, 0.01, 400), dates, cfg)
    none = criteria.event_study(shock + rng.normal(0, 0.01, 400), dates, cfg)
    assert real["passed"] and real["clusters"] == 40
    assert not none["passed"]
