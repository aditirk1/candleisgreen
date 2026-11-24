"""Phase 5 acceptance: a model update never changes risk limits or permissions, and a
contradicting paper opens a re-evaluation case. Plus the factory, governance, drift,
practitioner scoring and model levels B and C."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from candleisgreen.core.audit import AuditLog
from candleisgreen.core.config import DEFAULT_CONFIG_PATH, load_config
from candleisgreen.core.parameters import NotTunableError
from candleisgreen.research import factory, monitor
from candleisgreen.research.academic import load_osap
from candleisgreen.research.published import run_published_factor
from candleisgreen.research.registry import GovernanceError, ResearchRegistry

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
OSAP = ROOT / "tests" / "fixtures" / "osap"


@pytest.fixture
def reg(tmp_path):
    cfg = load_config()
    r = ResearchRegistry(tmp_path / "research.sqlite", AuditLog(tmp_path / "audit.sqlite"))
    ls, claims = load_osap(OSAP / "PredictorLSretWide_subset.parquet", OSAP / "SignalDoc_subset.csv")
    run_published_factor(claims["Mom12m"], ls["Mom12m"], "xs_momentum_12_1", r, cfg, NOW, "osap 2026.10")
    return cfg, r, ls, claims


LIBRARY_DEFS = {"xs_momentum_12_1": "cross sectional momentum past twelve month return skipping the most recent month",
                "st_reversal_5": "short term reversal previous week return"}


def _library(r):
    claims = {c["signal_id"]: c["claim_id"] for c in r.claims() if c.get("signal_id")}
    return factory.Library(LIBRARY_DEFS, claims)


def test_contradicting_paper_opens_a_reevaluation_case(reg):
    cfg, r, ls, claims = reg
    card = {"title": "Momentum crashes and the end of past twelve month return premia", "stance": "contradicts",
            "about_signal": "xs_momentum_12_1", "definition": "momentum fails after 2009", "data_required": []}
    digest = factory.run_daily([card], r, _library(r), set(), cfg, NOW)
    assert len(digest["reevaluations_opened"]) == 1 and digest["contradictions"][0]["signal_id"] == "xs_momentum_12_1"
    case = r.reevaluations("OPEN")[0]
    assert case["signal_id"] == "xs_momentum_12_1"
    links = r.links(digest["linked_to_signals"][0]["claim_id"])
    assert links[0]["relation"] == "contradicts"
    # Re-evaluation re-runs the tests on current data. It changes the tier, never a live weight.
    before = r.tier("xs_momentum_12_1")[0]
    factory.reevaluate(r, case["case_id"], lambda sid: {"passed": False, "note": "replication failed on current data"}, NOW)
    assert r.tier("xs_momentum_12_1")[0] == before - 1 and r.reevaluations("CLOSED")[0]["result"]["tier_after"] == before - 1


def test_factory_clusters_duplicates_flags_missing_data_and_links_near_duplicates(reg):
    cfg, r, ls, claims = reg
    cards = [
        {"title": "Analyst forecast dispersion predicts returns", "data_required": ["analyst estimates"], "definition": "x"},
        {"title": "Analyst forecast dispersion predicts returns", "data_required": ["analyst estimates"], "definition": "x"},
        {"title": "A new look at cross sectional momentum past twelve month return", "definition": "skipping the most recent month"},
        {"title": "Seasonal returns in industry portfolios", "data_required": [], "study_type": "reproduction"},
    ]
    d = factory.run_daily(cards, r, _library(r), {"osap"}, cfg, NOW)
    assert len(d["needs_data"]) == 1 and d["needs_data"][0]["free_substitute"]["analyst estimates"].startswith("none free")
    assert len(d["duplicates"]) == 1
    assert d["linked_to_signals"][0]["signal_id"] == "xs_momentum_12_1" and not d["reevaluations_opened"]
    assert len(d["new_hypotheses"]) == 1 and len(d["queued"]) == 1
    assert r.digests()[0]["date"] == "2026-11-24"


def test_factory_runs_a_builtin_study_and_records_negative_results(reg):
    cfg, r, ls, claims = reg
    from candleisgreen.research.academic import reproduce

    runner = lambda cid, card: reproduce(ls["BetaFP"], claims["BetaFP"], cfg)
    card = {"title": "Betting against beta", "data_required": ["osap"], "runner": "bab", "study_type": "reproduction"}
    d = factory.run_daily([card], r, _library(r), {"osap"}, cfg, NOW, {"bab": runner})
    assert d["results"] == [{"experiment_id": d["new_hypotheses"][0]["experiment_id"], "passed": False}]
    assert any(f["experiment_id"] == d["new_hypotheses"][0]["experiment_id"] for f in r.failures())


def test_promotion_above_tier_4_needs_aditi(reg):
    cfg, r, ls, claims = reg
    r.set_tier("xs_momentum_12_1", 4, "OOS_PASSED", {}, NOW)  # the system may go up to 4 on evidence
    with pytest.raises(GovernanceError):
        r.set_tier("xs_momentum_12_1", 5, "SHADOW", {}, NOW)
    pid = r.propose_promotion("xs_momentum_12_1", 5, {"shadow_days": 63}, NOW)
    with pytest.raises(GovernanceError):
        r.decide_promotion(pid, True, "system:research", NOW)
    r.decide_promotion(pid, True, "user:aditi", NOW)
    assert r.tier("xs_momentum_12_1")[0] == 5
    r.set_tier("xs_momentum_12_1", 3, "SUSPENDED", {}, NOW)  # demotion is automatic and allowed
    assert r.tier("xs_momentum_12_1")[0] == 3


def test_drift_alert_demotes_and_opens_a_case(reg):
    cfg, r, ls, claims = reg
    rng = np.random.default_rng(80)
    dead = rng.normal(-0.10 / 252, 0.10 / np.sqrt(252), 1000)
    out = monitor.check(r, "xs_momentum_12_1", dead, 0.08, 0.01 ** 2, 21, cfg, NOW)
    assert out["status"] == "alert" and out["tier_after"] == 2 and out["case_id"]
    fine = monitor.check(r, "st_reversal_5", rng.normal(0.05 / 252, 0.10 / np.sqrt(252), 252), 0.05, 0.02 ** 2, 5, cfg, NOW)
    assert fine["status"] in ("ok", "alert") and ("case_id" in fine) == (fine["status"] == "alert")


def test_practitioner_scoring(tmp_path):
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore
    from candleisgreen.research.practitioners import PractitionerBook, wilson
    from candleisgreen.sources import recorder
    from candleisgreen.sources.alpaca import AlpacaData
    from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

    cfg = load_config()
    now = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 19), AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca),
                      store, master, now, cfg)
    up, down = master.instrument_for_symbol("UPCO"), master.instrument_for_symbol("DNCO")
    book = PractitionerBook(tmp_path / "p.sqlite")
    start = datetime(2026, 1, 5, 21, 30, tzinfo=UTC)
    for k in range(40):
        made = start + timedelta(days=7 * k)
        book.add("src_trend", "trend", up, "up", 5, made, 0.7)
        book.add("src_trend", "trend", down, "down", 5, made, 0.7)
        if k < 10:
            book.add("src_new", "trend", up, "up", 5, made)
    book.resolve(store, now)
    strong = book.score("src_trend", "trend", cfg.research.criteria)
    young = book.score("src_new", "trend", cfg.research.criteria)
    assert young["track_record"] == "INSUFFICIENT DATA" and not young["eligible_as_signal"]
    assert strong["scored_claims"] >= 30 and strong["interval"][0] > 0.5 and strong["eligible_as_signal"]
    assert strong["brier"] is not None
    lo, hi = wilson(20, 30, 0.9)
    assert lo < 20 / 30 < hi


def test_walk_forward_purges_overlapping_targets():
    from candleisgreen.models import supervised

    T, N = 120, 5
    rng = np.random.default_rng(81)
    X = rng.normal(size=(T, N, 2))
    y = rng.normal(size=(T, N))
    seen = []

    class Spy:
        def fit(self, Xs, ys):
            seen.append(len(Xs))
        def predict(self, Xt):
            return np.zeros(len(Xt))

    supervised.walk_forward(X, y, lambda: Spy(), [0, 1], start=60, step=20, horizon=21)
    assert seen[0] == (60 - 21) * N  # days 0 to 38 only, so no target overlaps day 60


def test_levels_b_and_c_compete_and_synthetic_wins_nothing(reg):
    from candleisgreen.composite.v0 import _matrix
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore
    from candleisgreen.models import supervised
    from candleisgreen.research.champion import compare
    from candleisgreen.sources import recorder
    from candleisgreen.sources.alpaca import AlpacaData
    from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

    cfg, r, ls, claims = reg
    now = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 19), AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca),
                      store, master, now, cfg)
    ids, days, prices, volume, vendors = _matrix(store, master, now, date(2026, 11, 19))
    X, y, names = supervised.panel(prices)
    preds = {k: supervised.walk_forward(X, y, make, feats, start=300, step=21, horizon=21)
             for k, (make, feats) in supervised.MODELS.items()}
    mask = np.isfinite(y) & np.isfinite(preds[supervised.LEVEL_A]) & np.isfinite(preds[supervised.LEVEL_B]) & np.isfinite(preds[supervised.LEVEL_C])
    cid = r.claims()[0]["claim_id"]
    b_vs_a = compare(r, cid, supervised.LEVEL_A, supervised.LEVEL_B, y[mask], preds[supervised.LEVEL_A][mask],
                     preds[supervised.LEVEL_B][mask], nested=True, horizon=21, cfg=cfg, now=now, data_labels=("SYNTHETIC",))
    c_vs_b = compare(r, cid, supervised.LEVEL_B, supervised.LEVEL_C, y[mask], preds[supervised.LEVEL_B][mask],
                     preds[supervised.LEVEL_C][mask], nested=False, horizon=21, cfg=cfg, now=now, data_labels=("SYNTHETIC",))
    assert b_vs_a["test"].startswith("Clark-West") and c_vs_b["test"].startswith("Diebold-Mariano")
    assert b_vs_a["recommendation"] == "keep the champion" and c_vs_b["recommendation"] == "keep the champion"
    assert r.experiment(b_vs_a["experiment_id"])["status"] in ("PASSED", "FAILED")


def _fingerprint():
    cfg = load_config()
    files = [DEFAULT_CONFIG_PATH, ROOT / "config" / "parameters.yaml", ROOT / "config" / "models.yaml",
             ROOT / "config" / "licenses.yaml", ROOT / "config" / "capabilities.yaml"]
    return cfg.config_hash, cfg.risk.hard_limits.model_dump(), {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def test_model_updates_never_change_risk_limits_or_permissions(reg, tmp_path):
    from tests.phase1_env import risk_service

    cfg, r, ls, claims = reg
    before = _fingerprint()
    with risk_service(tmp_path / "risk") as (risk, _):
        limits_before = risk.health()["limits_hash"]
        # A full research day: factory, drift monitoring, a model comparison, and attempts to touch safeguards.
        factory.run_daily([{"title": "Momentum is dead", "stance": "contradicts", "about_signal": "xs_momentum_12_1"}],
                          r, _library(r), set(), cfg, NOW)
        monitor.check(r, "xs_momentum_12_1", np.full(300, -0.001), 0.08, 1e-4, 21, cfg, NOW)
        with pytest.raises(NotTunableError):
            r.preregister(r.claims()[0]["claim_id"], "economic",
                          {"varied_parameters": ["risk.hard_limits.daily_loss_stop_pct_equity"]}, NOW)
        with pytest.raises(NotTunableError):
            r.preregister(r.claims()[0]["claim_id"], "economic", {"varied_parameters": ["execution.live_trading_enabled"]}, NOW)
        with pytest.raises(GovernanceError):
            r.set_tier("xs_momentum_12_1", 6, "PAPER", {}, NOW)
        limits_after = risk.health()["limits_hash"]
        assert risk.health()["kill_switch"] is False
    assert _fingerprint() == before
    assert limits_after == limits_before
