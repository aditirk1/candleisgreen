"""Experiment lab: plain words become a pre-registered test through the same pipeline as a paper."""
from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.core.audit import AuditLog
from candleisgreen.research.registry import ResearchRegistry
from candleisgreen.teaching import experiment_lab
from tests.phase1_env import DECIDE_NOW, build_env

IDEA = "$UPCO shares will outperform over the next 5 days"


def test_design_states_null_data_and_holdout(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    out = experiment_lab.design(IDEA, env.store, env.master, env.cfg, DECIDE_NOW)
    plan = out["plan"]
    assert out["status"] == "DESIGNED" and out["card"]["instruments"] == ["UPCO"]
    assert plan["null_hypothesis"].startswith("The effect described has no positive return over 5 day")
    assert plan["data_available"][0].startswith("UPCO daily closes") and plan["data_missing"] == []
    assert "30%" in plan["out_of_sample"] and "Pass rule" in plan["out_of_sample"]
    missing = experiment_lab.design("$ZZZZ shares will underperform next week", env.store, env.master, env.cfg, DECIDE_NOW)
    assert missing["plan"]["data_missing"][0]["data"] == "ZZZZ daily closes"
    vague = experiment_lab.design("tech looks interesting", env.store, env.master, env.cfg, DECIDE_NOW)
    assert vague["status"] == "NEEDS INPUT"


def test_submit_preregisters_through_the_factory(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    reg = ResearchRegistry(tmp_path / "research.sqlite", AuditLog(tmp_path / "audit.sqlite"))
    designed = experiment_lab.design(IDEA, env.store, env.master, env.cfg, DECIDE_NOW)
    first = experiment_lab.submit(designed, reg, env.cfg, DECIDE_NOW)
    assert first["outcome"] == "new_hypotheses" and first["experiment_id"]
    assert reg.variant_count() >= 0 and any(c["card"].get("source_type") == "experiment_lab" for c in reg.claims())
    again = experiment_lab.submit(designed, reg, env.cfg, DECIDE_NOW)
    assert again["outcome"] == "duplicates"  # the same idea is linked, not tested twice
    reg.close()


def test_lab_through_the_api(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    env.store.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: DECIDE_NOW))
    assert api.post("/api/lab/design", json={"idea": IDEA}).json()["status"] == "DESIGNED"
    assert api.post("/api/lab/submit", json={"idea": "nothing to test"}).status_code == 400
    assert api.post("/api/lab/submit", json={"idea": IDEA}).json()["outcome"] == "new_hypotheses"
