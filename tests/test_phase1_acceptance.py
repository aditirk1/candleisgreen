"""Phase 1 acceptance: approval, rejection, fill, stale-feed block and kill switch, end to end.

Every test runs the risk engine in its own process through the risk service.
"""
import pytest

from candleisgreen.core.schemas import Venue
from candleisgreen.trading import execute_session, expire_unapproved, run_decision
from tests.phase1_env import (DECIDE_NOW, DECISION_DATE, EXEC_NOW, SESSION_DATE, build_env, quotes_for,
                              risk_service, simulator)


def _decide(env):
    return run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)


def _execute(env, risk, quotes=None, now=EXEC_NOW):
    return execute_session(SESSION_DATE, now, env.journal, quotes or quotes_for(env, now), risk, simulator(env),
                           env.store, env.master, env.cfg)


def test_decision_proposes_buys_for_uptrends_only(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    res = _decide(env)
    props = env.journal.proposals(SESSION_DATE)
    symbols = {p.symbol for p in props}
    assert res.forecasts >= 5 and props
    sides = {p.symbol: p.side for p in props}
    assert all(s in ("buy", "sell_short") for s in sides.values())
    assert sides.get("DNCO") == "sell_short" and "DLST" not in symbols  # downtrend shorted, delisted name ignored
    assert {"UPCO", "SPLT"} <= symbols


def test_approval_then_fill(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        target = next(p for p in env.journal.proposals(SESSION_DATE) if p.symbol == "UPCO")
        env.journal.approve(target.proposal_id, "user:aditi", EXEC_NOW)
        result = _execute(env, risk)
    assert result.submitted == (target.proposal_id,)
    assert env.journal.proposal(target.proposal_id).status == "filled"
    assert env.journal.positions()[target.instrument_id] == target.quantity
    unapproved = [p for p in env.journal.proposals(SESSION_DATE) if p.proposal_id != target.proposal_id]
    assert all(p.status == "proposed" for p in unapproved)  # nothing trades without approval in manual mode
    assert expire_unapproved(env.journal, SESSION_DATE, EXEC_NOW) == len(unapproved)
    assert env.audit.verify() is None


def test_rejection_means_no_order(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        for p in env.journal.proposals(SESSION_DATE):
            env.journal.reject(p.proposal_id, "user:aditi", EXEC_NOW)
        result = _execute(env, risk)
    assert result.submitted == () and env.journal.fills() == []
    assert all(p.status == "rejected" for p in env.journal.proposals(SESSION_DATE))


def test_auto_simulation_fills_inside_the_limits(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        result = _execute(env, risk)
    assert result.submitted
    equity = env.journal.cash() + sum(f["quantity"] * f["price"] for f in env.journal.fills())
    for f in env.journal.fills():
        assert f["quantity"] * f["price"] / equity <= env.cfg.risk.hard_limits.max_position_pct_equity + 1e-9
    # No cluster mapping exists yet, so every name sits in the UNKNOWN cluster and the
    # 20% cluster limit caps the whole book.
    invested = sum(f["quantity"] * f["price"] for f in env.journal.fills())
    assert invested / 100_000 <= env.cfg.risk.hard_limits.max_cluster_pct_equity + 1e-6
    assert all(f["slippage_bps"] is not None for f in env.journal.fills())


def test_stale_feed_blocks(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        result = _execute(env, risk, quotes_for(env, EXEC_NOW, age_seconds=30))
    assert result.submitted == () and env.journal.fills() == []
    assert result.blocked and all(any("stale quote" in r for r in rs) for rs in result.blocked.values())


def test_delayed_consolidated_quote_blocks(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        result = _execute(env, risk, quotes_for(env, EXEC_NOW, feed="sip_delayed"))
    assert result.submitted == ()


def test_kill_switch_blocks_then_release(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        assert risk.set_kill_switch(True, "user:aditi") is True
        blocked = _execute(env, risk)
        assert blocked.submitted == ()
        assert all(any("kill switch engaged" in r for r in rs) for rs in blocked.blocked.values())
        with pytest.raises(Exception):
            risk.set_kill_switch(False, "system:anyone")  # only Aditi can release it
        assert risk.health()["kill_switch"] is True


def test_risk_service_down_blocks_everything(tmp_path):
    from candleisgreen.risk.client import RiskClient

    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    dead = RiskClient("http://127.0.0.1:9", timeout=0.5)
    result = _execute(env, dead)
    assert result.submitted == ()
    assert all(any("unreachable" in r for r in rs) for rs in result.blocked.values())


def test_outside_window_blocks(tmp_path):
    from datetime import datetime, timezone

    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    late = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)  # 11:00 ET
    with risk_service(tmp_path / "risk") as (risk, _):
        result = _execute(env, risk, quotes_for(env, late), now=late)
    assert result.submitted == ()


def test_tier1_model_cannot_reach_a_paper_account(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        result = execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes_for(env, EXEC_NOW), risk, simulator(env),
                                 env.store, env.master, env.cfg, venue=Venue.PAPER)
    assert result.submitted == ()
    assert all(any("capital tier" in r for r in rs) for rs in result.blocked.values())


def test_rerunning_execution_does_not_repeat_orders(tmp_path):
    env = build_env(tmp_path, "auto_simulation")
    _decide(env)
    with risk_service(tmp_path / "risk") as (risk, _):
        first = _execute(env, risk)
        fills = len(env.journal.fills())
        second = _execute(env, risk)
    assert first.submitted and second.submitted == () and len(env.journal.fills()) == fills
