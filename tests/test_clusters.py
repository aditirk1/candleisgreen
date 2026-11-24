"""Correlation clusters and their stability test (spec decision Q7)."""
from datetime import date, datetime, timedelta, timezone

import numpy as np

from candleisgreen import clusters
from candleisgreen.core.config import load_config
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from tests.conftest import make_obs

UTC = timezone.utc


def _groups(rng, days, n_groups=3, per=5, noise=0.3):
    common = rng.normal(0, 0.01, (days, 1))
    blocks = [common + rng.normal(0, 0.01, (days, 1)) + noise * rng.normal(0, 0.01, (days, per)) for _ in range(n_groups)]
    return np.hstack(blocks)


def test_residual_clustering_recovers_planted_groups():
    rng = np.random.default_rng(1)
    r = _groups(rng, 252)
    labels = clusters.cluster_labels(clusters.residual_returns(r), 0.5)
    assert len(set(labels)) == 3
    for g in range(3):
        assert len(set(labels[g * 5:(g + 1) * 5])) == 1


def test_market_factor_alone_does_not_make_one_cluster():
    rng = np.random.default_rng(2)
    market = rng.normal(0, 0.01, (252, 1))
    r = market + rng.normal(0, 0.01, (252, 12))  # correlated only through the market
    labels = clusters.cluster_labels(clusters.residual_returns(r), 0.5)
    assert len(set(labels)) > 6


def test_stability_score():
    a = {f"s{i}": f"c{i // 5}" for i in range(15)}
    relabeled = {k: "x" + v for k, v in a.items()}
    assert clusters.stability(a, relabeled) == 1.0
    shuffled = {k: f"c{i % 3}" for i, k in enumerate(a)}
    assert clusters.stability(a, shuffled) < 0.2
    assert clusters.stability({"a": "1"}, {"a": "2"}) is None


def _store_with(tmp_path, returns, start=date(2025, 1, 2)):
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    master = InstrumentMaster(store.connection)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    names = [f"N{i:02d}" for i in range(returns.shape[1])]
    master.apply_snapshot([{"id": f"a{i}", "symbol": s, "exchange": "NYSE", "class": "us_equity", "status": "active",
                            "tradable": True, "name": s} for i, s in enumerate(names)], now)
    prices = 50 * np.cumprod(1 + returns, axis=0)
    obs = []
    for j, s in enumerate(names):
        iid = master.instrument_for_symbol(s)
        for t in range(prices.shape[0]):
            when = datetime.combine(start + timedelta(days=t), datetime.min.time(), tzinfo=UTC) + timedelta(hours=21)
            obs.append(make_obs(float(prices[t, j]), event=when, instrument=iid))
    store.add(obs)
    return store, master, names


def test_monthly_job_stores_runs_and_falls_back_when_unstable(tmp_path):
    cfg = load_config()
    rng = np.random.default_rng(3)
    store, master, names = _store_with(tmp_path, _groups(rng, 260))
    t1 = datetime(2025, 9, 30, 22, tzinfo=UTC)
    run1 = clusters.run(t1, store, master, cfg)
    assert run1.status == clusters.FIRST and len(set(run1.labels.values())) == 3
    assert clusters.run(t1 + timedelta(days=3), store, master, cfg).run_id == run1.run_id  # rerun is a no-op
    iid = master.instrument_for_symbol("N00")
    key, mode = clusters.cluster_key(store.connection, master, iid, t1)
    assert key == run1.labels[iid] and mode.startswith("clusters")
    same = clusters.run(t1 + timedelta(days=30), store, master, cfg, force=True)
    assert same.status == clusters.STABLE and same.stability > 0.9
    # Plant a regrouping: relabel stored members of the last stable run so the new run disagrees with it.
    store.connection.execute("UPDATE cluster_members SET cluster = 'c' || CAST((hash(instrument_id) % 7) AS VARCHAR) "
                             "WHERE run_id = ?", [same.run_id]).fetchall()
    shaken = clusters.run(t1 + timedelta(days=60), store, master, cfg, force=True)
    assert shaken.status == clusters.UNSTABLE
    key, mode = clusters.cluster_key(store.connection, master, iid, t1 + timedelta(days=60))
    assert key == "sector:UNKNOWN" and mode == "sector fallback"
    store.close()


def test_name_outside_a_stable_clustering_has_no_cluster(tmp_path):
    cfg = load_config()
    store, master, _ = _store_with(tmp_path, _groups(np.random.default_rng(4), 260))
    clusters.run(datetime(2025, 9, 30, 22, tzinfo=UTC), store, master, cfg)
    key, _ = clusters.cluster_key(store.connection, master, "inst_not_clustered", datetime(2025, 10, 1, tzinfo=UTC))
    assert key is None
    store.close()


def test_execution_blocks_a_name_outside_stable_clusters(tmp_path):
    from tests.phase1_env import DECIDE_NOW, DECISION_DATE, EXEC_NOW, SESSION_DATE, build_env, quotes_for, \
        risk_service, simulator
    from candleisgreen.trading import execute_session, run_decision

    env = build_env(tmp_path, "manual_simulation")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    run = clusters.run(DECIDE_NOW, env.store, env.master, env.cfg)
    props = {p.symbol: p for p in env.journal.proposals(SESSION_DATE)}
    covered, dropped = props["UPCO"], props["SPLT"]
    assert covered.instrument_id in run.labels and dropped.instrument_id in run.labels
    env.store.connection.execute("DELETE FROM cluster_members WHERE run_id = ? AND instrument_id = ?",
                                 [run.run_id, dropped.instrument_id]).fetchall()
    for p in (covered, dropped):
        env.journal.approve(p.proposal_id, "user:aditi", EXEC_NOW)
    with risk_service(tmp_path / "risk") as (risk, _):
        execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes_for(env, EXEC_NOW), risk, simulator(env),
                        env.store, env.master, env.cfg)
    assert env.journal.proposal(covered.proposal_id).status == "filled"
    blocked = env.journal.proposal(dropped.proposal_id)
    assert blocked.status == "blocked" and "cluster exposure cannot be evaluated" in blocked.reason
