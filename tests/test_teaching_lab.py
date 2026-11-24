"""Market autopsy, counterfactual, spaced review and the crisis library."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.core.config import load_config
from candleisgreen.teaching import lab
from candleisgreen.trading import execute_session, run_decision
from tests.phase1_env import (DECIDE_NOW, DECISION_DATE, EXEC_NOW, SESSION_DATE, build_env, quotes_for, risk_service,
                              simulator)

UTC = timezone.utc


def _filled_env(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    target = next(p for p in env.journal.proposals(SESSION_DATE) if p.symbol == "UPCO")
    env.journal.approve(target.proposal_id, "user:aditi", EXEC_NOW)
    with risk_service(tmp_path / "risk") as (risk, _):
        execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes_for(env, EXEC_NOW), risk, simulator(env),
                        env.store, env.master, env.cfg)
    return env


def test_autopsy_explains_a_simulated_fill(tmp_path):
    env = _filled_env(tmp_path)
    rows = lab.autopsy(env.journal, env.audit.records(), env.store, env.master, env.cfg, EXEC_NOW + timedelta(hours=1))
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "UPCO" and r["window"]["status"] == "OPEN"
    assert "trend" in r["expected_catalyst"] and r["spread_paid_bps"] is not None
    assert r["pnl"] is None and r["what_happened"].startswith("NOT AVAILABLE")  # no close after the fill yet
    from candleisgreen.sources import recorder
    from candleisgreen.sources.alpaca import AlpacaData
    from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

    later = datetime(2026, 11, 20, 21, 20, tzinfo=UTC)
    recorder.record_session(SESSION_DATE, AlpacaData(FakeAlpacaTransport(now=later), env.cfg.sources.alpaca),
                            env.store, env.master, later, env.cfg)
    r = lab.autopsy(env.journal, env.audit.records(), env.store, env.master, env.cfg, later + timedelta(hours=1))[0]
    p = r["pnl"]
    assert p["total_usd"] == pytest.approx(p["price_move_usd"] + p["spread_cost_usd"]) and p["spread_cost_usd"] <= 0
    assert p["market_usd"] is not None and p["specific_usd"] == pytest.approx(p["price_move_usd"] - p["market_usd"])
    assert r["assumptions"][0]["result"].startswith("NOT YET") and r["assumptions"][1]["result"] in ("HELD", "FAILED")


def test_counterfactual_is_labeled_and_uses_the_real_model(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    cfg = env.cfg
    base = lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "vol_multiplier", 1.0)
    assert base["label"] == "HYPOTHETICAL" and base["changed"] is False
    assert base["hypothetical"]["signal"] == pytest.approx(base["baseline"]["signal"], rel=1e-9)
    calmer = lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "vol_multiplier", 3.0)
    assert abs(calmer["hypothetical"]["signal"]) <= abs(calmer["baseline"]["signal"]) + 1e-9
    last = lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "last_price_pct", -50)
    assert last["changed"] is False and "skips the last" in last["note"]
    wide = lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "spread_bps", 500)
    assert wide["hypothetical"]["decision"] == "BLOCKED BY RISK" and wide["changed"] is True
    news = lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "remove_news", 0)
    assert news["changed"] is False and "not an input" in news["note"]
    assert lab.counterfactual(env.store, env.master, cfg, "NOPE", DECIDE_NOW, "vol_multiplier", 2)["status"] == "NOT AVAILABLE"
    with pytest.raises(ValueError):
        lab.counterfactual(env.store, env.master, cfg, "UPCO", DECIDE_NOW, "rewrite_history", 1)


def test_review_puts_wrong_predictions_first_and_respects_the_replay_clock(tmp_path):
    cfg = load_config()
    now = datetime(2026, 11, 24, 12, tzinfo=UTC)
    rev = lab.Review(tmp_path / "r.sqlite", cfg.teaching.review_intervals_days)
    preds = [
        {"prediction_id": "p1", "symbol": "UPCO", "direction": "up", "horizon_days": 5, "probability": 0.8, "outcome": 0,
         "made_at": "2026-10-01T21:30:00+00:00", "context": "replay"},
        {"prediction_id": "p2", "symbol": "DNCO", "direction": "down", "horizon_days": 5, "probability": 0.7, "outcome": 1,
         "made_at": "2026-10-01T21:30:00+00:00", "context": "replay"},
    ]
    gl = {"sharpe": {"plain": "Return per unit of swing", "meaning": "Mean over standard deviation"}}
    rev.sync("user:aditi", preds, gl, now, replay_clock=datetime(2026, 10, 3, tzinfo=UTC))
    assert [c["kind"] for c in rev.due("user:aditi", now)] == ["glossary"]  # outcome not revealed yet
    rev.sync("user:aditi", preds, gl, now, replay_clock=datetime(2026, 10, 8, tzinfo=UTC))
    due = rev.due("user:aditi", now)
    assert [c["kind"] for c in due] == ["wrong_prediction", "glossary"] and "UPCO" in due[0]["prompt"]
    up = rev.answer("user:aditi", due[0]["card_id"], True, now)
    assert up["box"] == 1 and up["due_at"].startswith("2026-11-27")
    down = rev.answer("user:aditi", due[0]["card_id"], False, now)
    assert down["box"] == 0
    rev.close()


def test_crisis_library_is_not_available_without_data(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    rows = lab.crisis_library(env.store, list(env.cfg.teaching.crises), DECIDE_NOW)
    assert len(rows) == 6 and all(r["status"] == "NOT AVAILABLE" for r in rows)
    assert rows[0]["reason"].startswith("Stored price data covers 2025")


def test_teaching_endpoints(tmp_path):
    env = _filled_env(tmp_path)
    env.store.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW + timedelta(hours=1)))
    assert api.get("/api/autopsy").json()["rows"][0]["symbol"] == "UPCO"
    cf = api.get("/api/counterfactual", params={"symbol": "UPCO", "change": "spread_bps", "amount": 500}).json()
    assert cf["label"] == "HYPOTHETICAL"
    assert api.get("/api/counterfactual", params={"symbol": "UPCO", "change": "bogus"}).status_code == 400
    cards = api.get("/api/review").json()["cards"]
    assert cards and all(c["kind"] == "glossary" for c in cards)
    assert api.post(f"/api/review/{cards[0]['card_id']}", json={"correct": True}).json()["box"] == 1
    assert all(e["status"] == "NOT AVAILABLE" for e in api.get("/api/crises").json()["episodes"])
