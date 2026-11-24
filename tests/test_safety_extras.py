"""Hard-limit change governance and the pre-open check."""
from datetime import date, datetime, timedelta, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.risk.limits import LimitBook, LimitChangeError

UTC = timezone.utc
T = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)


def _book(tmp_path):
    cfg = load_config()
    return LimitBook(tmp_path, cfg.risk.hard_limits, cfg.risk.loosening_delay_hours)


def test_tightening_applies_now(tmp_path):
    book = _book(tmp_path)
    assert book.request("max_position_pct_equity", 0.03, "user:aditi", T)["status"] == "APPLIED"
    assert book.effective().max_position_pct_equity == 0.03


def test_loosening_waits_24_hours_and_needs_confirmation(tmp_path):
    book = _book(tmp_path)
    out = book.request("max_position_pct_equity", 0.08, "user:aditi", T)
    assert out["status"] == "WAITING" and book.effective().max_position_pct_equity == 0.05
    with pytest.raises(LimitChangeError):
        book.confirm("max_position_pct_equity", "user:aditi", T + timedelta(hours=23))
    with pytest.raises(LimitChangeError):
        book.confirm("max_position_pct_equity", "system:anyone", T + timedelta(hours=25))
    book.confirm("max_position_pct_equity", "user:aditi", T + timedelta(hours=25))
    assert book.effective().max_position_pct_equity == 0.08


def test_only_aditi_can_request_and_values_are_checked(tmp_path):
    book = _book(tmp_path)
    with pytest.raises(LimitChangeError):
        book.request("max_spread_pct", 0.001, "system:research", T)
    with pytest.raises(ValueError):
        book.request("max_spread_pct", 2.0, "user:aditi", T)
    with pytest.raises(ValueError):
        book.request("execution_grade_feeds", 1.0, "user:aditi", T)


def test_risk_service_uses_changed_limits(tmp_path):
    import json
    import urllib.request

    from tests.phase1_env import risk_service

    with risk_service(tmp_path / "risk") as (risk, _):
        before = risk.health()["limits_hash"]
        req = urllib.request.Request(risk.base_url + "/limits/request", method="POST",
                                     data=json.dumps({"key": "max_order_pct_adv20", "value": 0.005, "actor": "user:aditi"}).encode(),
                                     headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req).read())["status"] == "APPLIED"
        assert risk.health()["limits_hash"] != before
        bad = urllib.request.Request(risk.base_url + "/limits/request", method="POST",
                                     data=json.dumps({"key": "max_order_pct_adv20", "value": 0.5, "actor": "system:x"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(Exception):
            urllib.request.urlopen(bad)


def test_preopen_cancels_risky_buys_and_never_adds(tmp_path):
    from candleisgreen import preopen
    from candleisgreen.trading import run_decision
    from tests.phase1_env import DECIDE_NOW, DECISION_DATE, SESSION_DATE, build_env

    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    props = env.journal.proposals(SESSION_DATE)
    target = props[0]
    count = len(props)
    out = preopen.run(SESSION_DATE, datetime(2026, 11, 20, 14, 0, tzinfo=UTC), DECIDE_NOW, env.journal, env.master,
                      halted={props[1].symbol}, filings_since=lambda iid, since: ["8-K"] if iid == target.instrument_id else [])
    assert {c["proposal_id"] for c in out} == {target.proposal_id, props[1].proposal_id}
    assert env.journal.proposal(target.proposal_id).status == "cancelled"
    assert len(env.journal.proposals(SESSION_DATE)) == count  # nothing added
