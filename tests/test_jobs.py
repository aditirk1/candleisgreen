"""Spec decision Q13: jobs are safe to rerun, catch up after gaps, and the fallback uses the heartbeat."""
from datetime import date, datetime, timezone

from candleisgreen import jobs
from candleisgreen.core.config import load_config

UTC = timezone.utc


def test_record_twice_stores_the_same_result(tmp_path):
    now = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    first = jobs.run("record", tmp_path, fake=True, now=now)
    again = jobs.run("record", tmp_path, fake=True, now=now)
    assert first["observations_added"] > 0 and again["observations_added"] == 0
    assert jobs.read_heartbeat(tmp_path)["status"] == "ok"


def test_catch_up_fills_missed_days_and_skips_weekends(tmp_path):
    jobs.run("record", tmp_path, fake=True, now=datetime(2026, 11, 13, 21, 20, tzinfo=UTC))  # Friday
    out = jobs.run("catch-up", tmp_path, fake=True, now=datetime(2026, 11, 19, 21, 20, tzinfo=UTC))  # Thursday
    assert out["sessions"] == ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"]
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore

    store = PointInTimeStore(tmp_path / "pit.duckdb")
    flag = InstrumentMaster(store.connection).completeness(date(2026, 11, 17))[0]
    assert flag["collection_mode"] == "backfill"  # collected late, and labeled so
    store.close()


def test_fallback_runs_only_when_the_heartbeat_is_stale(tmp_path):
    cfg = load_config()
    t1 = datetime(2026, 11, 18, 21, 20, tzinfo=UTC)
    jobs.run("record", tmp_path, fake=True, now=t1)
    fresh = jobs.run("fallback", tmp_path, fake=True, now=datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    assert fresh["ran"] is False
    later = datetime(2026, 11, 19, 23, 30, tzinfo=UTC)  # more than 26 hours after the last run
    assert jobs.heartbeat_stale(tmp_path, later, cfg.sources.recorder.heartbeat_max_age_hours)
    out = jobs.run("fallback", tmp_path, fake=True, now=later)
    assert out["ran"] is True and out["sessions"] == ["2026-11-19"]


def test_missing_heartbeat_counts_as_stale(tmp_path):
    assert jobs.heartbeat_stale(tmp_path, datetime(2026, 11, 19, tzinfo=UTC), 26)


def test_no_session_is_recorded_before_the_free_data_is_ready():
    cfg = load_config()
    assert jobs.last_collectable_session(datetime(2026, 11, 19, 21, 10, tzinfo=UTC), cfg) == date(2026, 11, 18)
    assert jobs.last_collectable_session(datetime(2026, 11, 19, 21, 16, tzinfo=UTC), cfg) == date(2026, 11, 19)
