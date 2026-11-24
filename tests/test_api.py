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


def test_replay_and_predictions_through_the_api(tmp_path):
    from candleisgreen.trading import run_decision

    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    env.store.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW))
    assert api.get("/api/replay", params={"symbol": "UPCO", "cursor": "2027-01-01T00:00:00+00:00"}).status_code == 400
    view = api.get("/api/replay", params={"symbol": "UPCO", "cursor": "2026-10-01T21:30:00+00:00"}).json()
    assert max(p["date"] for p in view["prices"]) <= "2026-10-01"
    pid = api.post("/api/predictions", json={"symbol": "UPCO", "direction": "up", "horizon_days": 5, "probability": 0.7,
                                             "replay_cursor": "2026-10-01T21:30:00+00:00"}).json()["prediction_id"]
    early = api.get("/api/predictions", params={"cursor": "2026-10-02T21:30:00+00:00"}).json()
    assert early["predictions"][0]["status"] == "NOT YET REVEALED" and early["calibration"]["resolved"] == 0
    later = api.get("/api/predictions", params={"cursor": "2026-10-08T21:30:00+00:00"}).json()
    assert later["predictions"][0]["outcome"] in (0, 1) and later["calibration"]["resolved"] == 1
    why = api.get("/api/reasoning", params={"symbol": "DNCO"}).json()
    assert why["why_not"] and "not positive" in why["why_not"]


def test_workstation_screens_through_the_api(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    env.store.close()
    with risk_service(tmp_path / "risk") as (risk, _):
        api = TestClient(create_app(tmp_path, risk.base_url, env.cfg, clock=lambda: EXEC_NOW))
        opp = api.get("/api/opportunities").json()
        assert opp["session_date"] == SESSION_DATE.isoformat() and opp["rows"]
        assert all(r["expected_return"].startswith("NOT AVAILABLE") for r in opp["rows"])
        mk = api.get("/api/markets", params={"symbol": "UPCO"}).json()
        assert mk["selected"]["symbol"] == "UPCO" and mk["history"]
        assert max(h["date"] for h in mk["history"]) <= EXEC_NOW.date().isoformat()
        assert api.get("/api/backtests").json()["rows"] == []
        ex = api.get("/api/experts").json()
        assert ex["sources"] and ex["practitioner_note"].startswith("NOT AVAILABLE")
        au = api.get("/api/audit").json()
        assert au["chain_ok"] and au["records"] and au["parameters"]
        assert au["limits"]["effective"]
        key = "max_position_pct_equity"
        assert key in au["limits"]["editable"]
        current = au["limits"]["effective"][key]
        changed = api.post("/api/limits/request", json={"key": key, "value": current * 0.5}).json()
        assert changed["status"] == "APPLIED"
        waiting = api.post("/api/limits/request", json={"key": key, "value": current}).json()
        assert waiting["status"] == "WAITING"
        assert api.post("/api/limits/confirm", json={"key": key}).status_code == 400
        st = api.get("/api/settings").json()
        assert st["monthly_cost_usd"] == 0 and {c["name"] for c in st["credentials"]} >= {"APCA_API_KEY_ID"}
        assert all(c["status"] in ("SET", "NOT SET") for c in st["credentials"])
