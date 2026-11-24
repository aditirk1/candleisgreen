"""Workstation API: approvals, rejections and the kill switch go through it end to end."""
from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.trading import execute_session, run_decision
from tests.phase1_env import (DECIDE_NOW, DECISION_DATE, EXEC_NOW, SESSION_DATE, build_env, quotes_for,
                              risk_service, simulator)


def test_overview_and_execution_through_the_api(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    with risk_service(tmp_path / "risk") as (risk, _):
        api = TestClient(create_app(tmp_path, risk.base_url, env.cfg, clock=lambda: EXEC_NOW))
        status = api.get("/api/status").json()
        assert status["venue"] == "SIMULATION" and status["risk_service"]["status"] == "OK"
        queue = api.get("/api/execution").json()["approval_queue"]
        assert queue
        first, second = queue[0], queue[1]
        assert api.post(f"/api/proposals/{first['proposal_id']}/approve").json()["status"] == "approved"
        assert api.post(f"/api/proposals/{second['proposal_id']}/reject").json()["status"] == "rejected"
        assert api.post(f"/api/proposals/{second['proposal_id']}/approve").status_code == 409
        execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes_for(env, EXEC_NOW), risk, simulator(env),
                        env.store, env.master, env.cfg)
        ex = api.get("/api/execution").json()
        statuses = {o["proposal_id"]: o["status"] for o in ex["orders"]}
        assert statuses[first["proposal_id"]] == "filled" and statuses[second["proposal_id"]] == "rejected"
        assert ex["fills"] and ex["reconciliation"]["status"] == "MATCHED"
        assert ex["execution_quality"] and ex["execution_quality"][0]["fills"] >= 1
        ov = api.get("/api/overview").json()
        assert ov["positions"] and 0 < ov["risk_in_use"]["invested_pct"] < 0.2
        assert api.post("/api/kill-switch", json={"engaged": True}).json()["kill_switch"] is True
        assert api.get("/api/execution").json()["kill_switch"] is True


def test_api_reports_an_unreachable_risk_service(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW))
    assert api.get("/api/status").json()["risk_service"]["status"] == "UNREACHABLE"
    assert api.post("/api/kill-switch", json={"engaged": True}).status_code == 503
