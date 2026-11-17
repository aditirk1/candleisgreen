"""Phase 0: point-in-time reads, and the planted lookahead leak that must be caught."""
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from candleisgreen.data.pit_store import LookaheadError, PointInTimeStore, assert_no_lookahead
from candleisgreen.models import fixture_baseline
from tests.conftest import make_obs

UTC = timezone.utc
DECISION = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)


def _days(n):
    start = datetime(2026, 11, 9, 21, 0, tzinfo=UTC)
    return [make_obs(value=50.0 + i, event=start + timedelta(days=i)) for i in range(n)]


def test_as_of_view_hides_values_not_yet_usable():
    store = PointInTimeStore()
    store.add(_days(8))  # closes from Nov 9 to Nov 16
    seen = store.as_of(DECISION).series("inst_TEST", "close")
    assert [o.value for o in seen] == [50.0, 51.0, 52.0, 53.0, 54.0]
    assert all(o.first_usable_at < DECISION for o in seen)


def test_boundary_is_strict():
    store = PointInTimeStore()
    event = DECISION - timedelta(minutes=15)
    store.add([make_obs(event=event, usable=DECISION)])  # usable exactly at decision time
    assert store.as_of(DECISION).series("inst_TEST", "close") == []


def test_duplicates_are_ignored_and_rows_are_append_only():
    store = PointInTimeStore()
    assert store.add(_days(3)) == 3
    assert store.add(_days(3)) == 0
    assert store.count() == 3


def test_revised_value_is_invisible_before_its_revision():
    """Failure fixture: lookahead from a revised filing."""
    event = datetime(2026, 8, 1, 20, 0, tzinfo=UTC)
    original = make_obs(value=1.00, event=event, usable=event + timedelta(hours=1), vintage=0, field="eps")
    revised = make_obs(value=0.60, event=event, usable=event + timedelta(days=45), vintage=1, field="eps")
    store = PointInTimeStore()
    store.add([revised, original])
    before = store.as_of(event + timedelta(days=10)).series("inst_TEST", "eps")
    after = store.as_of(event + timedelta(days=60)).series("inst_TEST", "eps")
    assert [o.value for o in before] == [1.00]
    assert [o.value for o in after] == [0.60]


def test_planted_lookahead_leak_is_caught():
    """Phase 0 acceptance: a model fed data from after the decision time fails the build."""
    store = PointInTimeStore()
    store.add(_days(8))
    leaked = store.unsafe_all("inst_TEST", "close")  # bypasses the as-of view
    assert any(o.first_usable_at >= DECISION for o in leaked)
    with pytest.raises(LookaheadError):
        fixture_baseline.issue_forecast("inst_TEST", leaked, DECISION, issued_at=DECISION, horizon_days=5)


def test_guard_passes_clean_inputs_and_names_the_offender():
    clean = _days(3)
    assert_no_lookahead(clean, DECISION)
    late = make_obs(event=DECISION + timedelta(days=1))
    with pytest.raises(LookaheadError, match=late.observation_id):
        assert_no_lookahead(clean + [late], DECISION)


def test_parquet_export_round_trips(tmp_path):
    store = PointInTimeStore()
    store.add(_days(4))
    target = tmp_path / "observations.parquet"
    store.export_parquet(target)
    count = duckdb.connect().execute(f"SELECT count(*) FROM '{target.as_posix()}'").fetchone()[0]
    assert count == 4
