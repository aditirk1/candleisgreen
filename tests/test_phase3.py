"""Phase 3 acceptance: full evidence chain, a stored negative result, and a Composite whose
output traces to each signal's weight and evidence. Academic data: trimmed real Open Source
Asset Pricing files (CC BY 4.0)."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from candleisgreen.core.audit import AuditLog
from candleisgreen.core.config import load_config
from candleisgreen.core.parameters import NotTunableError
from candleisgreen.research.academic import load_osap
from candleisgreen.research.published import run_published_factor
from candleisgreen.research.registry import PlanFrozenError, PlanNotRegisteredError, ResearchRegistry

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
OSAP = Path(__file__).parent / "fixtures" / "osap"
BETA_NOTE = ("Chosen as the expected failure because the dataset rates its reconstruction 3_distant. "
             "The reproduction table was viewed before choosing, so this is not a blind pre-registration.")


@pytest.fixture
def research(tmp_path):
    cfg = load_config()
    ls, claims = load_osap(OSAP / "PredictorLSretWide_subset.parquet", OSAP / "SignalDoc_subset.csv")
    reg = ResearchRegistry(tmp_path / "research.sqlite", AuditLog(tmp_path / "audit.sqlite"))
    mom = run_published_factor(claims["Mom12m"], ls["Mom12m"], "xs_momentum_12_1", reg, cfg, NOW, "osap 2026.10")
    rev = run_published_factor(claims["STreversal"], ls["STreversal"], "st_reversal_5", reg, cfg, NOW, "osap 2026.10")
    bab = run_published_factor(claims["BetaFP"], ls["BetaFP"], "betting_against_beta", reg, cfg, NOW, "osap 2026.10",
                               selection_note=BETA_NOTE)
    return cfg, reg, mom, rev, bab


def test_momentum_reproduces_and_replicates(research):
    cfg, reg, mom, rev, bab = research
    assert mom["reproduction"]["passed"] and mom["replication"]["passed"]
    assert mom["tier"] == 3 and reg.tier("xs_momentum_12_1")[0] == 3
    assert mom["reproduction"]["fraction_of_paper"] > 0.9  # 1.28% against the paper's 1.31% a month


def test_expected_failure_is_stored_and_visible(research):
    cfg, reg, mom, rev, bab = research
    assert not bab["reproduction"]["passed"] and bab["tier"] == 1
    failures = reg.failures()
    assert [f["experiment_id"] for f in failures] == [bab["reproduction"]["experiment_id"]]
    assert failures[0]["selection_note"].startswith("Chosen as the expected failure")
    assert reg.claim(bab["claim_id"])["status"] == "FAILED"


def test_academic_evidence_stops_at_tier_3(research):
    cfg, reg, mom, rev, bab = research
    assert max(reg.tier(s)[0] for s in ("xs_momentum_12_1", "st_reversal_5")) == 3


def test_evidence_chain_links_claim_experiments_and_results(research):
    cfg, reg, mom, rev, bab = research
    chain = reg.chain(mom["claim_id"])
    assert chain["claim"]["card"]["reported_effect"]["monthly_return_pct"] == 1.31
    assert [e["study_type"] for e in chain["experiments"]] == ["reproduction", "replication"]
    assert {l["relation"] for l in chain["links"]} == {"reproduces", "replicates"}
    assert all(e["variants"] == 1 for e in chain["experiments"])


def test_registry_rules(research, tmp_path):
    cfg, reg, mom, rev, bab = research
    cid = mom["claim_id"]
    plan = {"study": "x", "varied_parameters": ["composite.eligibility.min_prob_positive"]}
    eid = reg.preregister(cid, "economic", plan, NOW)
    with pytest.raises(PlanNotRegisteredError):
        reg.complete(eid, plan, True, {}, NOW)  # nothing recorded yet
    with pytest.raises(NotTunableError):
        reg.preregister(cid, "economic", {"varied_parameters": ["risk.hard_limits.max_position_pct_equity"]}, NOW)
    with pytest.raises(NotTunableError):
        reg.record_variant(eid, {"risk.hard_limits.max_spread_pct": 0.01}, {}, NOW)
    reg.record_variant(eid, {"composite.eligibility.min_prob_positive": 0.7}, {"m": 1}, NOW)
    with pytest.raises(PlanFrozenError):
        reg.complete(eid, {**plan, "study": "changed"}, True, {}, NOW)
    reg.complete(eid, plan, False, {"note": "kept"}, NOW)
    with pytest.raises(PlanFrozenError):
        reg.record_variant(eid, {}, {}, NOW)
    with pytest.raises(PlanNotRegisteredError):
        reg.experiment("exp_never")
    assert reg.variant_count() == 6  # three reproductions, two replications, and this one


def test_composite_v0_traces_weights_to_evidence(research, tmp_path):
    from candleisgreen.composite.v0 import SIGNALS, build
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore
    from candleisgreen.sources import recorder
    from candleisgreen.sources.alpaca import AlpacaData
    from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

    cfg, reg, mom, rev, bab = research
    now = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 19), AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca),
                      store, master, now, cfg)
    rec = build(store, master, reg, cfg, date(2026, 11, 19), now)
    by_id = {s["signal_id"]: s for s in rec["signals"]}
    assert set(by_id) == set(SIGNALS)
    for sid, s in by_id.items():
        assert {"weight", "capital_weight", "mu_hat", "prob_positive", "tier", "experiments", "scores"} <= set(s)
        assert s["data_labels"] == ["SYNTHETIC"] and s["record_type"] == "retrospective"
        assert not s["eligible"] and s["capital_weight"] == 0.0
        assert any("SYNTHETIC" in r for r in s["reasons"])
    assert by_id["xs_momentum_12_1"]["experiments"] == [mom["reproduction"]["experiment_id"], mom["replication"]["experiment_id"]]
    assert by_id["xs_momentum_12_1"]["academic_record"]["months"] > 300
    assert any("PROVISIONAL" in r or "SAFEGUARD" in r for r in by_id["xs_momentum_12_1"]["reasons"])
    assert by_id["ts_momentum_252_21"]["scores"]["validity"].startswith("NOT AVAILABLE")
    assert rec["unallocated_weight"] == pytest.approx(1.0)  # nothing is eligible, nothing trades
    assert set(rec["benchmarks"]) == {"challenger_equal_weight", "frozen_weight"}
    assert reg.latest_run()["composite_run_id"] == rec["composite_run_id"]
