"""Spec principles 3 and 11: missing capabilities are labeled and refused."""
import pytest
from pydantic import ValidationError

from candleisgreen.core.capabilities import (
    Capability, CapabilityNotAvailableError, Status, load_capabilities,
)


def test_map_loads_and_every_gap_has_a_reason():
    caps = load_capabilities()
    for name, cap in caps.capabilities.items():
        if cap.status is not Status.AVAILABLE:
            assert cap.reason, name


@pytest.mark.parametrize("name", [
    "options_trading", "realtime_consolidated_quotes", "intraday_trading",
    "analyst_consensus_estimates", "licensed_news", "non_us_execution",
])
def test_features_without_free_data_are_refused(name):
    caps = load_capabilities()
    with pytest.raises(CapabilityNotAvailableError, match="NOT AVAILABLE"):
        caps.require(name)


def test_free_options_and_crypto_data_are_limited_not_refused():
    """Alpaca's free indicative options feed and crypto data exist. Missing code was never proof of missing data."""
    caps = load_capabilities()
    for name in ("options_data_and_flow", "crypto_data", "futures_data"):
        assert caps.require(name).status is Status.LIMITED


def test_core_research_and_paper_execution_are_available():
    caps = load_capabilities()
    assert caps.require("us_factor_research").status is Status.AVAILABLE
    assert caps.require("paper_execution_us").status is Status.AVAILABLE
    assert caps.require("us_daily_bars").label.startswith("LIMITED")


def test_a_gap_without_a_reason_is_rejected():
    with pytest.raises(ValidationError):
        Capability(status="not_available")
    with pytest.raises(ValidationError):
        Capability(status="limited", sources=("x",))
    with pytest.raises(KeyError):
        load_capabilities().get("crystal_ball")
