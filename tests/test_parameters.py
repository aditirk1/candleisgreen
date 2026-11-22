"""Empirical results, safeguards and provisional settings are kept apart."""
import pytest
from pydantic import ValidationError

from candleisgreen.core.parameters import (
    Basis, NotTunableError, Parameter, load_registry, unclassified,
)


def test_every_config_value_is_classified_and_nothing_extra():
    missing, extra = unclassified()
    assert missing == [], f"classify these in config/parameters.yaml: {missing}"
    assert extra == [], f"no longer in config: {extra}"


def test_hard_limits_and_live_switch_are_safeguards():
    reg = load_registry()
    for path, param in reg.parameters.items():
        if path.startswith("risk."):
            assert param.basis is Basis.SAFEGUARD, path
    assert reg.get("execution.live_trading_enabled").basis is Basis.SAFEGUARD


def test_research_thresholds_are_not_dressed_up_as_evidence():
    reg = load_registry()
    for path in ("composite.eligibility.min_prob_positive", "composite.eligibility.min_oos_days",
                 "composite.monitoring.alert_probability", "composite.monitoring.review_window_days",
                 "universe.min_price", "time.execution_window_start_local"):
        assert reg.get(path).basis is Basis.PROVISIONAL, path
    assert reg.label("composite.eligibility.min_prob_positive") == "PROVISIONAL"


def test_empirical_values_cite_their_source():
    reg = load_registry()
    empirical = reg.paths(Basis.EMPIRICAL)
    assert "composite.edge.delta_us_published" in empirical
    assert "McLean and Pontiff" in reg.label("composite.edge.delta_us_published")


def test_experiments_cannot_vary_safeguards_or_facts():
    reg = load_registry()
    reg.assert_tunable("composite.eligibility.min_prob_positive")
    reg.assert_tunable("composite.edge.delta_us_published")
    with pytest.raises(NotTunableError):
        reg.assert_tunable("risk.hard_limits.max_position_pct_equity")
    with pytest.raises(NotTunableError):
        reg.assert_tunable("composite.costs.sec_fee_per_million_usd_sold")


def test_each_basis_requires_its_own_evidence():
    with pytest.raises(ValidationError):
        Parameter(basis="empirical")
    with pytest.raises(ValidationError):
        Parameter(basis="provisional")
    with pytest.raises(ValidationError):
        Parameter(basis="external_fact", source="x")
    with pytest.raises(ValidationError):
        Parameter(basis="safeguard")
    with pytest.raises(KeyError):
        load_registry().get("composite.made_up")
