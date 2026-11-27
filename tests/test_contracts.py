"""Phase 0: time rules, IDs, config and typed schemas."""
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml
from pydantic import ValidationError

from candleisgreen.core import timeutil
from candleisgreen.core.config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from candleisgreen.core.ids import make_id
from candleisgreen.core.schemas import CalibrationStatus, Forecast, OrderIntent
from tests.conftest import make_intent, make_obs

UTC = timezone.utc


def test_naive_datetime_is_rejected():
    with pytest.raises(timeutil.NaiveDatetimeError):
        timeutil.ensure_utc(datetime(2026, 11, 16, 12, 0))
    with pytest.raises(ValidationError):
        make_obs(event=datetime(2026, 11, 9, 21, 0))


def test_decision_time_handles_daylight_saving():
    winter = timeutil.local_to_utc(date(2026, 11, 16), "16:30", "America/New_York")
    summer = timeutil.local_to_utc(date(2026, 7, 1), "16:30", "America/New_York")
    assert (winter.hour, summer.hour) == (21, 20)


def test_daylight_saving_boundary_times_are_rejected():
    with pytest.raises(timeutil.InvalidLocalTimeError):  # spring forward gap
        timeutil.local_to_utc(date(2026, 3, 8), "02:30", "America/New_York")
    with pytest.raises(timeutil.InvalidLocalTimeError):  # fall back overlap
        timeutil.local_to_utc(date(2026, 11, 1), "01:30", "America/New_York")


def test_micros_round_trip():
    moment = datetime(2026, 11, 16, 21, 30, 0, 123456, tzinfo=UTC)
    assert timeutil.from_micros(timeutil.to_micros(moment)) == moment


def test_ids_are_content_derived_and_stable():
    a, b = make_obs(value=50.0), make_obs(value=50.0)
    assert a.observation_id == b.observation_id
    assert make_obs(value=50.01).observation_id != a.observation_id
    assert make_obs(vintage=1).observation_id != a.observation_id
    assert make_id("x", {"b": 1, "a": 2}) == make_id("x", {"a": 2, "b": 1})


def test_contracts_are_immutable():
    obs = make_obs()
    with pytest.raises(ValidationError):
        obs.value = 99.0
    intent = make_intent()
    with pytest.raises(ValidationError):
        intent.quantity = 1_000_000.0


def test_first_usable_at_cannot_precede_knowledge():
    event = datetime(2026, 11, 9, 21, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        make_obs(event=event, usable=event - timedelta(seconds=1))


def test_missing_flag_must_match_value():
    assert make_obs(value=None).missing_flag is True


def _forecast(**overrides):
    as_of = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)
    base = dict(
        model_id="m", model_version="1", asset_id="a", issued_at=as_of, as_of=as_of,
        target_definition="t", target_start=as_of, target_end=as_of + timedelta(days=5),
        signal_strength=1.0, training_cutoff=as_of, data_snapshot_id="snap_x", feature_snapshot_id="feat_x",
        calibration_status=CalibrationStatus.SIGNAL_STRENGTH_ONLY, eligible_for_orders=False,
    )
    base.update(overrides)
    return Forecast(**base)


def test_uncalibrated_forecast_cannot_state_an_expected_return():
    assert _forecast().forecast_id.startswith("fc_")
    with pytest.raises(ValidationError):
        _forecast(signal_strength=None, expected_excess_return=0.01)
    with pytest.raises(ValidationError):
        _forecast(expected_excess_return=0.01)  # both outputs set


def test_forecast_cannot_train_past_its_as_of():
    as_of = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)
    with pytest.raises(ValidationError):
        _forecast(training_cutoff=as_of + timedelta(seconds=1))


def test_order_venue_can_only_be_simulation_or_paper():
    with pytest.raises(ValidationError):
        OrderIntent(forecast_id="f", asset_id="a", side="buy", quantity=1, strategy_id="s",
                    strategy_version="1", session_date="2026-11-16", venue="LIVE")


def test_rationale_is_at_most_six_lines():
    with pytest.raises(ValidationError):
        OrderIntent(forecast_id="f", asset_id="a", side="buy", quantity=1, strategy_id="s",
                    strategy_version="1", session_date="2026-11-16", venue="SIMULATION",
                    rationale=tuple(str(i) for i in range(7)))


def test_config_loads_and_hashes(cfg):
    assert cfg.spec_version == "3.2"
    assert cfg.config_hash == load_config().config_hash


def test_hard_limits_match_the_spec_defaults(limits):
    """Guards against an accidental edit of a hard risk limit."""
    assert limits.model_dump() == {
        "max_position_pct_equity": 0.05, "max_cluster_pct_equity": 0.20, "max_order_pct_adv20": 0.01,
        "max_spread_pct": 0.005, "daily_loss_stop_pct_equity": 0.02, "max_quote_age_seconds": 15.0,
        # Short selling ships off. Aditi turns it on through the limit workflow.
        "max_short_position_pct_equity": 0.0, "max_short_exposure_pct_equity": 0.0,
        "max_gross_exposure_pct_equity": 1.0,
        "execution_grade_feeds": ("iex_realtime", "fixture_realtime"),
    }
    assert "sip_delayed" not in limits.execution_grade_feeds


def _raw():
    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_config_rejects_unknown_keys():
    raw = _raw()
    raw["risk"]["hard_limits"]["surprise"] = 1
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_config_refuses_to_enable_live_trading():
    raw = _raw()
    raw["execution"]["live_trading_enabled"] = True
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)
    raw = _raw()
    raw["execution"]["mode"] = "live"
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)
