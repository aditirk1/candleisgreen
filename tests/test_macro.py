"""Macro vintages from the FRED API: what was known then, never a later revision."""
from datetime import datetime, timezone

from candleisgreen.core.config import load_config
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.global_research import FRED_API_FIXTURES, macro_view, refresh_macro
from candleisgreen.sources import macro

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)


def _fred(cfg):
    fc = cfg.sources.fred
    return fc.model_copy(update={"series": tuple(s for s in fc.series if s.id == "UNRATE")})


def test_every_vintage_is_stored_and_reads_are_as_known_then(tmp_path):
    cfg = load_config()
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    added = macro.refresh(store, macro.FixtureFredTransport(FRED_API_FIXTURES), _fred(cfg), NOW)
    assert added == {"UNRATE": 5}
    assert macro.refresh(store, macro.FixtureFredTransport(FRED_API_FIXTURES), _fred(cfg), NOW) == {"UNRATE": 0}

    def july(when):
        return [o for o in store.as_of(when).series("macro:UNRATE", "value") if o.event_time.month == 7]

    assert july(datetime(2026, 8, 3, 12, tzinfo=UTC))[0].value == 4.2  # first release
    assert july(datetime(2026, 9, 10, 12, tzinfo=UTC))[0].value == 4.3  # revision, vintage 1
    assert july(datetime(2026, 7, 31, 12, tzinfo=UTC)) == []  # not yet released
    # Released on 2026-11-06, usable only from 17:00 New York time that day.
    early = store.as_of(datetime(2026, 11, 6, 21, 59, tzinfo=UTC)).series("macro:UNRATE", "value")[-1]
    late = store.as_of(datetime(2026, 11, 6, 22, 1, tzinfo=UTC)).series("macro:UNRATE", "value")[-1]
    assert early.event_time.month == 9 and late.event_time.month == 10
    store.close()


def test_non_numeric_value_is_missing_never_filled(tmp_path):
    cfg = load_config()
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    macro.refresh(store, macro.FixtureFredTransport(FRED_API_FIXTURES), _fred(cfg), NOW)
    sept = [o for o in store.as_of(NOW).series("macro:UNRATE", "value") if o.event_time.month == 9][0]
    assert sept.value is None and sept.missing_flag
    store.close()


def test_paging_reads_every_row():
    class Paged(macro.FixtureFredTransport):
        calls = 0

        def get(self, path, params):
            Paged.calls += 1
            return super().get(path, params)

    rows = macro.all_vintages(Paged(FRED_API_FIXTURES), "UNRATE", page=2)
    assert len(rows) == 5 and Paged.calls == 3


def test_no_key_means_not_available(tmp_path, monkeypatch):
    cfg = load_config()
    monkeypatch.delenv(cfg.sources.fred.api_key_env, raising=False)
    out = refresh_macro(tmp_path, NOW, cfg, fake=False)
    assert out["status"] == "NOT AVAILABLE" and "FRED_API_KEY" in out["reason"]
    assert not (tmp_path / "pit.duckdb").exists()


def test_view_shows_latest_known_value_with_its_vintage(tmp_path):
    cfg = load_config()
    refresh_macro(tmp_path, NOW, cfg, fake=True)
    store = PointInTimeStore(tmp_path / "pit.duckdb", read_only=True)
    rows = {r["series"]: r for r in macro_view(store, cfg, NOW)}
    store.close()
    assert rows["UNRATE"]["period"] == "2026-10-01" and rows["UNRATE"]["value"] == 4.4
    assert rows["UNRATE"]["license"] == "fred_terms"
    assert rows["CPIAUCSL"]["status"] == "NOT AVAILABLE"
