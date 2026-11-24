"""Tier 5 shadow tracking: prospective by construction, frozen expectations, promotion only through Aditi."""
from datetime import datetime, timedelta, timezone

import pytest

from candleisgreen.core.audit import AuditLog
from candleisgreen.core.config import load_config
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.research.registry import GovernanceError, ResearchRegistry
from candleisgreen.research.shadow import ShadowBook
from tests.conftest import make_obs

UTC = timezone.utc
START = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


def _store(tmp_path, days):
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    obs = []
    for t in range(days + 2):
        when = START + timedelta(days=t)
        obs.append(make_obs(100 * 1.001 ** t, event=when, instrument="inst_A"))
        obs.append(make_obs(50.0, event=when, instrument="inst_B"))
    store.add(obs)
    return store


def _run(book, sid, days, late_day=None):
    for t in range(days):
        as_of = START + timedelta(days=t)
        start = as_of + timedelta(hours=17, minutes=30)  # next session open
        issued = as_of + timedelta(minutes=30) if t != late_day else start + timedelta(hours=1)
        book.record_targets(sid, as_of, issued, start, {"inst_A": 1.0 if t % 2 == 0 else 0.5, "inst_B": 0.0})


def _setup(tmp_path, days, late_day=None):
    cfg = load_config()
    store = _store(tmp_path, days)
    book = ShadowBook(tmp_path / "shadow.sqlite", cfg)
    assert book.register("sig_test", 0.12, 0.03, START)
    assert not book.register("sig_test", 0.50, 0.01, START)  # the expectation stays frozen
    _run(book, "sig_test", days, late_day)
    book.mark(store, START + timedelta(days=days + 2))
    reg = ResearchRegistry(tmp_path / "research.sqlite", AuditLog(tmp_path / "audit.sqlite"))
    return cfg, store, book, reg


def test_a_clean_prospective_record_passes_and_waits_for_aditi(tmp_path):
    cfg, store, book, reg = _setup(tmp_path, 70)
    rec = book.record("sig_test")
    assert rec.prospective and rec.trading_days == 70 and rec.trades == 70
    assert rec.band_low_annual < rec.realized_mean_annual < rec.band_high_annual
    assert 0 < rec.tracking_error_annual < 0.001  # only the first day, built from empty, costs more
    out = book.evaluate("sig_test", reg, START + timedelta(days=72))
    assert out["passed"] and out["proposal_id"]
    again = book.evaluate("sig_test", reg, START + timedelta(days=73))
    assert again["proposal_id"] == out["proposal_id"]  # one proposal, not one per day
    with pytest.raises(GovernanceError):
        reg.decide_promotion(out["proposal_id"], True, "system:shadow", START + timedelta(days=73))
    assert reg.promotions()[0]["status"] == "PENDING"
    store.close(), book.close(), reg.close()


def test_a_short_record_is_not_promoted(tmp_path):
    cfg, store, book, reg = _setup(tmp_path, 30)
    out = book.evaluate("sig_test", reg, START + timedelta(days=32))
    assert not out["passed"] and any("minimum 63" in r for r in out["reasons"]) and out["proposal_id"] is None
    store.close(), book.close(), reg.close()


def test_one_late_target_makes_the_record_retrospective(tmp_path):
    cfg, store, book, reg = _setup(tmp_path, 70, late_day=40)
    out = book.evaluate("sig_test", reg, START + timedelta(days=72))
    assert not out["passed"] and any("retrospective" in r for r in out["reasons"])
    store.close(), book.close(), reg.close()


def test_unregistered_strategy_cannot_record(tmp_path):
    book = ShadowBook(tmp_path / "shadow.sqlite", load_config())
    with pytest.raises(ValueError):
        book.record_targets("nope", START, START, START + timedelta(hours=1), {"inst_A": 1.0})
    book.close()
