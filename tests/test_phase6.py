"""Phase 6 acceptance: every non-US instrument is research only and cannot receive orders,
and a week of follow-the-sun research jobs runs with no manual step. Also the FX split."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.risk.engine import evaluate
from candleisgreen.sources import fx
from tests.conftest import make_ctx, make_intent

UTC = timezone.utc
FRED = Path(__file__).parent / "fixtures" / "fred"


def test_fx_split_adds_up():
    s = fx.split(100.0, 110.0, 1.10, 1.21)
    assert s.local_return == pytest.approx(0.10) and s.fx_return == pytest.approx(0.10)
    assert s.usd_return == pytest.approx(0.21) and s.local_return + s.fx_return + s.cross == pytest.approx(s.usd_return)


def test_real_fred_rates_and_inversion():
    table = fx.FxTable({"EUR": fx.parse_fred_csv((FRED / "DEXUSEU.csv").read_text()),
                        "JPY": fx.parse_fred_csv((FRED / "DEXJPUS.csv").read_text())})
    day = max(table.rates["EUR"])
    assert 0.8 < table.usd_per_unit("EUR", day) < 1.6  # USD per euro
    jpy_day = max(table.rates["JPY"])
    assert table.usd_per_unit("JPY", jpy_day) < 0.05  # FRED quotes yen per dollar, inverted here


def test_missing_fx_rate_is_never_filled():
    """Spec failure fixture: missing FX rate."""
    table = fx.FxTable({"EUR": {date(2026, 11, 20): 1.10}})
    with pytest.raises(fx.MissingFxRateError):
        table.usd_per_unit("EUR", date(2026, 11, 21))
    with pytest.raises(fx.MissingFxRateError):
        table.usd_per_unit("CHF", date(2026, 11, 20))
    assert fx.usd_split(table, "EUR", 100, 101, date(2026, 11, 20), date(2026, 11, 21)) is None


@pytest.mark.parametrize("tag,verdict", [("direct", "approved"), ("proxy", "approved"), ("research_only", "blocked"), (None, "blocked")])
def test_only_direct_and_proxy_instruments_can_receive_orders(tag, verdict, limits):
    assert evaluate(make_intent(), make_ctx(instrument_tag=tag), limits).verdict.value == verdict


def test_taxonomy_tags_us_listings_direct_and_everything_else_research_only():
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore

    cfg = load_config()
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    now = datetime(2026, 11, 24, tzinfo=UTC)
    m = master.apply_snapshot([
        {"id": "a1", "symbol": "USCO", "name": "US Company Inc", "exchange": "NYSE", "status": "active", "tradable": True},
        {"id": "a2", "symbol": "FORY", "name": "Foreign Bank ADR", "exchange": "NYSE", "status": "active", "tradable": True},
        {"id": "a3", "symbol": "7203", "name": "Toyota Motor", "exchange": "XTKS", "status": "active", "tradable": False},
    ], now)
    sec_only = master.map_issuer("0000999999", None, now)
    tags = {s: master.tag(i, cfg.markets.us_exchanges) for s, i in m.items()}
    assert tags == {"USCO": "direct", "FORY": "proxy", "7203": "research_only"}
    assert master.tag(sec_only, cfg.markets.us_exchanges) == "research_only"
    assert master.tag("inst_unknown", cfg.markets.us_exchanges) == "research_only"


def test_nyse_calendar_from_the_rule_table():
    from candleisgreen import calendars

    assert not calendars.is_trading_day(date(2026, 11, 26))  # Thanksgiving
    assert calendars.is_early_close(date(2026, 11, 27)) and calendars.is_trading_day(date(2026, 11, 27))
    assert not calendars.is_trading_day(date(2026, 7, 3))  # Independence Day observed
    assert calendars.tradable("XNYS") and not calendars.tradable("XTKS") and not calendars.tradable("XLON")


def test_every_non_us_exchange_in_the_rule_table_is_research_only():
    from candleisgreen import calendars

    for mic, rule in calendars.rules().items():
        if not mic.startswith("XN"):
            assert rule["tag"] == "research_only", mic


def test_momentum_evidence_by_market_is_tagged_research_only():
    import pandas as pd
    from candleisgreen import global_research

    files = sorted((Path(__file__).parent / "fixtures" / "jkp").glob("*.csv"))
    df = pd.concat([global_research.load_jkp(f) for f in files])
    res = {r["location"]: r for r in global_research.market_tiers(df, "ret_12_1", 1993)}
    assert set(res) == {"usa", "gbr", "deu", "jpn", "hkg"}
    assert all(r["license"] == "cc_by_nc_4_0" for r in res.values())
    assert all(r["months"] > 300 for r in res.values())
    from candleisgreen.core.licenses import LicenseNotPermittedError, load_licenses

    with pytest.raises(LicenseNotPermittedError):
        load_licenses().assert_use(["cc_by_nc_4_0"], "paper_trading")  # derived results cannot reach an order


def test_a_week_of_follow_the_sun_jobs_runs_with_no_manual_step(tmp_path):
    """Phase 6 acceptance part 2."""
    from candleisgreen import jobs, scheduler

    jobs.run("record", tmp_path, fake=True, now=datetime(2026, 11, 13, 21, 20, tzinfo=UTC))
    report = scheduler.run_week(date(2026, 11, 14), tmp_path, fake=True)
    assert report.ok, report.failures
    assert len(report.runs) == 7 * 6
    cluster_runs = [r["detail"]["run_id"] for r in report.runs if r["job"] == "clusters"]
    assert len(set(cluster_runs)) == 1  # computed once, then reused until the refresh is due
    assert {r["slot"] for r in report.runs} == {"asia_pacific", "europe", "us_preopen", "us", "overnight_review"}
    preopen_runs = [r["detail"] for r in report.runs if r["job"] == "preopen"]
    assert sum(1 for d in preopen_runs if d["ran"]) == 5 and all(d.get("cancelled", []) == [] for d in preopen_runs)
    recorded = [r for r in report.runs if r["job"] == "record"]
    sessions = sorted({s for r in recorded for s in r["detail"].get("sessions", [])})
    assert "2026-11-26" not in sessions  # Thanksgiving is skipped by the calendar
    assert sessions[:3] == ["2026-11-16", "2026-11-17", "2026-11-18"]
    for name in ("global_factors", "fx", "preopen", "record", "review", "clusters"):
        assert jobs.read_heartbeat(tmp_path / "heartbeats" / name)["status"] == "ok"
    again = scheduler.run_week(date(2026, 11, 14), tmp_path, fake=True)  # rerunning the week changes nothing
    assert again.ok and all(not r["detail"].get("sessions") for r in again.runs if r["job"] == "record")
