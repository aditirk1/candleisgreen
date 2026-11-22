"""Phase 0 acceptance: one offline event flows end to end with immutable IDs."""
import json

import pytest

from candleisgreen.core.audit import AuditLog
from candleisgreen.core.schemas import Venue
from candleisgreen.pipeline import NotEligibleForOrdersError, build_intent, run_offline_event
from tests.conftest import FIXTURE


def test_event_flows_end_to_end(tmp_path):
    result = run_offline_event(FIXTURE, tmp_path / "run")
    assert result["risk_verdict"] == "approved"
    assert result["venue"] == "SIMULATION"
    assert len(result["fill_ids"]) == 1
    assert result["positions"] == {"inst_TEST": 48.0}
    assert result["audit_chain_ok"] is True

    log = AuditLog(tmp_path / "run" / "audit.sqlite")
    records = log.records()
    kinds = [r["event_type"] for r in records]
    assert kinds == ["observation_ingested"] * 6 + [
        "forecast_issued", "order_intent_created", "risk_decision", "broker_ack", "fill",
    ]
    by_kind = {r["event_type"]: json.loads(r["payload_json"]) for r in records}
    # Every step points at the one before it.
    assert by_kind["forecast_issued"]["data_snapshot_id"] == result["data_snapshot_id"]
    assert by_kind["order_intent_created"]["forecast_id"] == result["forecast_id"]
    assert by_kind["risk_decision"]["client_order_id"] == result["client_order_id"]
    assert by_kind["fill"]["client_order_id"] == result["client_order_id"]
    from candleisgreen.core.config import load_config

    cfg = load_config()
    expected = f"config:{cfg.config_version}:{cfg.config_hash}"
    assert all(r["actor"] and r["strategy_version"] == expected for r in records)


def test_ids_are_identical_across_independent_runs(tmp_path):
    first = run_offline_event(FIXTURE, tmp_path / "a")
    second = run_offline_event(FIXTURE, tmp_path / "b")
    assert first == second
    assert first["audit_head"] == second["audit_head"]


def test_forecast_used_only_data_known_at_decision_time(tmp_path):
    result = run_offline_event(FIXTURE, tmp_path / "run")
    # Six closes are in the store. The Nov 16 close is after the Nov 13 decision time.
    assert len(result["observation_ids"]) == 6
    log = AuditLog(tmp_path / "run" / "audit.sqlite")
    forecast = [json.loads(r["payload_json"]) for r in log.records() if r["event_type"] == "forecast_issued"][0]
    assert forecast["as_of"] == "2026-11-13T21:30:00.000000Z"
    # Closes known at decision time rise from 50.00 to 51.20, so the sign is +1.
    # The Nov 16 close of 49.00 would flip it to -1 if it leaked in.
    assert forecast["signal_strength"] == 1.0
    assert forecast["calibration_status"] == "signal_strength_only"


def _variant(tmp_path, mutate):
    payload = json.loads(FIXTURE.read_text())
    mutate(payload)
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(payload))
    return path


def test_stale_quote_blocks_and_nothing_fills(tmp_path):
    path = _variant(tmp_path, lambda p: p["execution"]["quote"].update(quote_time="2026-11-16T14:39:30Z"))
    result = run_offline_event(path, tmp_path / "run")
    assert result["risk_verdict"] == "blocked"
    assert result["fill_ids"] == []
    assert any("stale quote" in r for r in result["risk_reasons"])
    kinds = [r["event_type"] for r in AuditLog(tmp_path / "run" / "audit.sqlite").records()]
    assert "risk_decision" in kinds and "fill" not in kinds and "broker_ack" not in kinds


def test_kill_switch_blocks(tmp_path):
    path = _variant(tmp_path, lambda p: p["execution"].update(kill_switch_engaged=True))
    result = run_offline_event(path, tmp_path / "run")
    assert result["risk_verdict"] == "blocked" and result["fill_ids"] == []


def test_falling_prices_give_no_order(tmp_path):
    def falling(p):
        for i, bar in enumerate(p["bars"]):
            bar["value"] = 60.0 - i

    result = run_offline_event(_variant(tmp_path, falling), tmp_path / "run")
    assert result["client_order_id"] is None and result["fill_ids"] == []


def test_fixture_model_cannot_be_routed_to_a_paper_broker(tmp_path):
    from datetime import datetime, timezone

    from candleisgreen.models import fixture_baseline
    from tests.conftest import make_obs

    decision = datetime(2026, 11, 13, 21, 30, tzinfo=timezone.utc)
    closes = [make_obs(value=50.0), make_obs(value=51.0, event=datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc))]
    forecast = fixture_baseline.issue_forecast("inst_TEST", closes, decision, decision, 5)
    with pytest.raises(NotEligibleForOrdersError):
        build_intent(forecast, 10.0, "2026-11-16", Venue.PAPER, 51.0)
