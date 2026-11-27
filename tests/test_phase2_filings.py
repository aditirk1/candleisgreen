"""Phase 2 acceptance part 2: every financial figure traces to an SEC filing, and no beat without a consensus."""
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.earnings import scorecard
from candleisgreen.sources import sec

UTC = timezone.utc
FIX = Path(__file__).parent / "fixtures" / "sec"
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def loaded():
    cfg = load_config()
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    client = sec.SecClient(sec.FixtureSecTransport(FIX), cfg.sources.sec)
    info = sec.ingest_issuer(client, "320193", "AAPL", store, master, NOW, cfg)
    return cfg, store, master, info


def test_every_figure_traces_to_a_filing(loaded):
    cfg, store, master, info = loaded
    rows = store.connection.execute(
        "SELECT source_ref, first_usable_at, published_at FROM observations WHERE vendor = 'sec'").fetchall()
    assert len(rows) == info["observations_added"] > 50
    for ref, usable, published in rows:
        accn, form, url = ref.split(" ", 2)
        assert len(accn) == 20 and accn.count("-") == 2
        assert url.startswith("https://www.sec.gov/Archives/edgar/data/320193/") and url.endswith(f"{accn}-index.htm")
        assert usable == published


def test_figures_become_usable_at_the_acceptance_time(loaded):
    cfg, store, master, info = loaded
    iid = info["instrument_id"]
    field = "us-gaap:EarningsPerShareDiluted:USD/shares:2026-06-28"
    obs = store.as_of(NOW).series(iid, field)
    if not obs:  # the three-month Q3 period in the fixture starts the day after Q2 ended
        fields = [f for (f,) in store.connection.execute(
            "SELECT DISTINCT field FROM observations WHERE field LIKE 'us-gaap:EarningsPerShareDiluted%2026-06-2%'").fetchall()]
        obs = store.as_of(NOW).series(iid, fields[0]) if fields else []
    q = [o for o in store.as_of(NOW).series(iid, "us-gaap:EarningsPerShareDiluted:USD/shares:2026-03-29")]
    assert q and q[-1].value == 2.02
    accepted = q[-1].first_usable_at
    subs = json.loads((FIX / "data.sec.gov__submissions__CIK0000320193.json").read_text())
    r = subs["filings"]["recent"]
    i = r["accessionNumber"].index("0000320193-26-000020")
    assert accepted == datetime.fromisoformat(r["acceptanceDateTime"][i].replace("Z", "+00:00"))
    assert store.as_of(accepted).series(iid, "us-gaap:EarningsPerShareDiluted:USD/shares:2026-03-29") == []


def test_restatement_becomes_a_new_vintage():
    cfg = load_config()
    facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 1.00, "accn": "0000000001-25-000001", "form": "10-Q", "filed": "2025-05-01"},
        {"start": "2025-01-01", "end": "2025-03-31", "val": 1.00, "accn": "0000000001-26-000001", "form": "10-K", "filed": "2026-02-01"},
        {"start": "2025-01-01", "end": "2025-03-31", "val": 0.90, "accn": "0000000001-26-000009", "form": "10-Q/A", "filed": "2026-03-01"},
    ]}}}}}
    obs = sec.facts_to_observations("1", "inst_x", facts, {}, NOW, cfg)
    assert [(o.value, o.vintage) for o in obs] == [(1.0, 0), (0.9, 1)]
    store = PointInTimeStore()
    store.add(obs)
    field = obs[0].field
    assert store.as_of(datetime(2025, 6, 1, tzinfo=UTC)).series("inst_x", field)[-1].value == 1.0
    assert store.as_of(datetime(2026, 3, 5, tzinfo=UTC)).series("inst_x", field)[-1].value == 0.9


def test_unknown_acceptance_time_uses_the_filing_date_cutoff():
    cfg = load_config()
    t = sec.published_time({"filed": "2025-05-01"}, None, cfg.sources.sec)
    assert t == datetime(2025, 5, 1, 21, 30, tzinfo=UTC)  # 17:30 ET


def test_scorecard_has_no_beat_or_miss(loaded):
    cfg, store, master, info = loaded
    rows = scorecard(store, info["instrument_id"], NOW)
    assert rows and all(r.vs_consensus is None for r in rows)
    text = json.dumps([asdict(r) for r in rows], default=str).lower()
    assert "beat" not in text and "miss" not in text
    assert rows[0].vs_consensus_label.startswith("NOT AVAILABLE")
    latest = rows[0]
    assert latest.source and latest.eps_yoy_change is not None and latest.revenue_yoy_pct is not None


def test_scorecard_only_shows_what_was_filed_by_then(loaded):
    cfg, store, master, info = loaded
    early = scorecard(store, info["instrument_id"], datetime(2024, 6, 1, tzinfo=UTC))
    late = scorecard(store, info["instrument_id"], NOW)
    assert len(early) < len(late)
    assert all(r.filed_at <= datetime(2024, 6, 1, tzinfo=UTC) for r in early)


def test_sic_maps_to_fama_french_12_with_version_and_date(loaded):
    cfg, store, master, info = loaded
    assert info["industry"] == "BusEq"  # SIC 3571 Electronic Computers
    rec = master.classifications(info["instrument_id"])[0]
    assert rec["mapping_version"] == "french-siccodes12-2026-11-24" and rec["sic_code"] == 3571
    assert master.sector_at(info["instrument_id"], datetime(2026, 1, 1, tzinfo=UTC)) == "UNKNOWN"  # before it was classified
    assert master.sector_at(info["instrument_id"], NOW) == "BusEq"


@pytest.mark.parametrize("sic,expected", [(3571, ("BusEq", "known")), ("2834", ("Hlth", "known")), (6022, ("Money", "known")),
                                          (1520, ("Other", "known")), (None, ("UNKNOWN", "unknown")), ("", ("UNKNOWN", "unknown")),
                                          (0, ("UNKNOWN", "unknown")), ("abc", ("UNKNOWN", "unknown"))])
def test_ff12_mapping(sic, expected):
    _, industries = sec.load_ff12()
    assert sec.ff12_for(sic, industries) == expected


def test_live_sec_transport_needs_a_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(sec.MissingUserAgentError):
        sec.HttpSecTransport(load_config().sources.sec)


def test_execution_quality_by_window():
    from candleisgreen.execution_quality import by_window

    fills = [{"filled_at": "2026-11-20T14:40:00Z", "slippage_bps": 5.0}, {"filled_at": "2026-11-20T14:50:00Z", "slippage_bps": 3.0},
             {"filled_at": "2026-11-20T15:10:00Z", "slippage_bps": 8.0}, {"filled_at": "2026-11-20T15:20:00Z", "slippage_bps": 6.0}]
    stats = {s.window: s for s in by_window(fills, 30)}
    assert stats["09:30 to 10:00 ET"].mean_bps == 4.0 and stats["10:00 to 10:30 ET"].fills == 2
    lo, hi = stats["09:30 to 10:00 ET"].interval_95
    assert lo < 4.0 < hi
