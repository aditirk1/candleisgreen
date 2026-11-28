"""Company intelligence: every metric has a source, a period and its age, or a NOT AVAILABLE reason."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.core.config import load_config
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.sources.sec import FixtureSecTransport, SecClient, ingest_issuer
from tests.phase1_env import EXEC_NOW, ROOT, build_env

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 15, tzinfo=UTC)


def _with_apple(tmp_path):
    cfg = load_config()
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    master = InstrumentMaster(store.connection)
    client = SecClient(FixtureSecTransport(ROOT / "tests" / "fixtures" / "sec"), cfg.sources.sec)
    ingest_issuer(client, "320193", "AAPL", store, master, NOW, cfg)
    store.close()
    return cfg


def _check_metric(m):
    if m["status"] == "OK":
        assert m["source"] and m["period"] and m["as_of"] and m["age_days"] >= 0 and m["value"] is not None
    else:
        assert m["status"] == "NOT AVAILABLE" and m["reason"]


def test_sec_company_page_has_sourced_metrics_and_honest_gaps(tmp_path):
    cfg = _with_apple(tmp_path)
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", cfg, clock=lambda: NOW))
    c = api.get("/api/company/AAPL").json()
    assert c["status"] == "OK" and c["profile"]["name"] == "Apple Inc."
    assert "Electronic Computers" in c["profile"]["description"] and c["profile"]["industry_code"] == "BusEq"
    assert c["profile"]["revenue_model"].startswith("NOT AVAILABLE")
    for m in list(c["fundamentals"].values()) + list(c["valuation"].values()):
        _check_metric(m)
    rev = c["fundamentals"]["revenue"]
    assert rev["status"] == "OK" and "sec.gov" in rev["source"] and rev["period"].startswith("quarter")
    assert c["valuation"]["pe"]["status"] == "NOT AVAILABLE" and c["valuation"]["pe"]["reason"] == "No recorded price"
    assert c["valuation"]["pb"]["reason"].startswith("Shares outstanding are not collected")
    assert any(r["risk"] == "Company-reported risk factors" and "NOT AVAILABLE" in r["detail"] for r in c["risks"])
    assert c["signals"]["system_view"].startswith("NOT AVAILABLE")
    assert c["catalysts"] == [] and "No free earnings" in c["catalyst_note"]


def test_priced_company_without_filings(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    env.store.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW))
    c = api.get("/api/company/UPCO").json()
    assert c["price"]["value"] > 0 and c["price"]["source"] == "alpaca_synthetic"
    assert all(m["status"] == "NOT AVAILABLE" for m in c["fundamentals"].values())
    assert c["valuation"]["pe"]["status"] == "NOT AVAILABLE"
    assert any(r["risk"] == "Demo data" for r in c["risks"]) and any(r["risk"] == "Price swings" for r in c["risks"])
    assert "uptrend" in c["signals"]["system_view"]
    assert api.get("/api/company/NOPE").json()["status"] == "NOT AVAILABLE"


def test_price_to_earnings_needs_every_input_with_a_source():
    from candleisgreen import company as co

    price = {"value": 100.0, "date": "2026-11-20", "source": "alpaca", "as_of_dt": NOW}
    ttm = {"status": "OK", "value": 5.0, "period": "2025-10-01 to 2026-09-30", "source": "0000320193-26-000026", "as_of": NOW.isoformat()}
    pe = co.valuation({"eps_ttm": ttm}, price, NOW)["pe"]
    assert pe["status"] == "OK" and pe["value"] == 20.0 and "alpaca" in pe["source"] and "0000320193" in pe["source"]
    loss = co.valuation({"eps_ttm": {**ttm, "value": -1.0}}, price, NOW)["pe"]
    assert loss["status"] == "NOT AVAILABLE" and "negative" in loss["reason"]
