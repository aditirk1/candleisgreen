"""A scheduled trading day: decision after the close, execution in the window, expiry at its end."""
from datetime import datetime, timezone

from candleisgreen import operations
from tests.phase1_env import DECISION_DATE, SESSION_DATE, build_env, risk_service

UTC = timezone.utc
DECIDE_AT = datetime(2026, 11, 19, 21, 31, tzinfo=UTC)   # 16:31 ET
EXECUTE_AT = datetime(2026, 11, 20, 14, 36, tzinfo=UTC)  # 09:36 ET, inside the window
EXPIRE_AT = datetime(2026, 11, 20, 15, 30, tzinfo=UTC)   # 10:30 ET


def _env(tmp_path, mode):
    env = build_env(tmp_path, mode)
    env.store.close()
    env.journal.close()
    return env


def test_auto_simulation_day_runs_without_a_manual_step(tmp_path):
    env = _env(tmp_path, "auto_simulation")
    with risk_service(tmp_path / "risk") as (risk, _):
        cfg = env.cfg.model_copy(update={"execution": env.cfg.execution.model_copy(update={"risk_service_url": risk.base_url})})
        d = operations.decide(DECIDE_AT, tmp_path, cfg, fake=True)
        assert d["ran"] and d["decision_date"] == DECISION_DATE.isoformat() and d["proposals"] >= 2
        assert d["composite"].get("run_id") or d["composite"]["status"] == "NOT AVAILABLE"
        e = operations.execute(EXECUTE_AT, tmp_path, cfg, fake=True)
        assert e["ran"] and e["venue"] == "SIMULATION" and e["submitted"] >= 1
        again = operations.execute(EXECUTE_AT, tmp_path, cfg, fake=True)
        assert again["submitted"] == 0  # nothing is sent twice
    j = operations._journal(tmp_path, cfg)
    assert j.fills() and all(f["venue"] == "SIMULATION" for f in j.fills())
    j.close()


def test_manual_mode_waits_for_approval_then_expires(tmp_path):
    env = _env(tmp_path, "manual_simulation")
    with risk_service(tmp_path / "risk") as (risk, _):
        cfg = env.cfg.model_copy(update={"execution": env.cfg.execution.model_copy(update={"risk_service_url": risk.base_url})})
        operations.decide(DECIDE_AT, tmp_path, cfg, fake=True)
        e = operations.execute(EXECUTE_AT, tmp_path, cfg, fake=True)
        assert e["submitted"] == 0
    out = operations.expire(EXPIRE_AT, tmp_path, cfg, fake=True)
    j = operations._journal(tmp_path, cfg)
    assert out["expired"] >= 2 and all(p.status == "expired" for p in j.proposals(SESSION_DATE))
    j.close()


def test_unreachable_risk_service_blocks_every_order(tmp_path):
    env = _env(tmp_path, "auto_simulation")
    cfg = env.cfg.model_copy(update={"execution": env.cfg.execution.model_copy(update={"risk_service_url": "http://127.0.0.1:9"})})
    operations.decide(DECIDE_AT, tmp_path, cfg, fake=True)
    e = operations.execute(EXECUTE_AT, tmp_path, cfg, fake=True)
    assert e["submitted"] == 0 and e["blocked"] >= 1
    j = operations._journal(tmp_path, cfg)
    assert j.fills() == []
    j.close()


def test_research_mode_makes_no_proposals(tmp_path):
    env = _env(tmp_path, "research")
    assert operations.decide(DECIDE_AT, tmp_path, env.cfg, fake=True)["ran"] is False
    assert operations.execute(EXECUTE_AT, tmp_path, env.cfg, fake=True)["ran"] is False


def test_weekend_and_holiday_do_nothing(tmp_path):
    env = _env(tmp_path, "auto_simulation")
    saturday = datetime(2026, 11, 21, 21, 31, tzinfo=UTC)
    thanksgiving = datetime(2026, 11, 26, 14, 36, tzinfo=UTC)
    assert operations.decide(saturday, tmp_path, env.cfg, fake=True)["ran"] is False
    assert operations.execute(thanksgiving, tmp_path, env.cfg, fake=True)["ran"] is False
