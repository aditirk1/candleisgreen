"""Insider (Form 4), institutional (13F) and large-holder filings: transaction and disclosure dates kept apart."""
from datetime import datetime, timezone

import duckdb

from candleisgreen.core.config import load_config
from candleisgreen.sources import ownership as own
from candleisgreen.sources.sec import FixtureSecTransport, SecClient
from tests.phase1_env import ROOT

UTC = timezone.utc
FIX = ROOT / "tests" / "fixtures"


def _client(folder):
    return SecClient(FixtureSecTransport(FIX / folder), load_config().sources.sec)


def test_real_form4_parses_with_both_dates_and_the_plan_flag():
    xml = (FIX / "sec_insiders" / "www.sec.gov__Archives__edgar__data__320193__000114036126045775__form4.xml").read_bytes()
    rows = own.parse_form4(xml, "0001140361-26-045775", datetime(2026, 11, 25, 23, 30, 25, tzinfo=UTC), "u")
    assert rows and rows[0]["issuer_ticker"] == "AAPL" and rows[0]["owner_name"] == "Newstead Jennifer"
    r = rows[0]
    assert r["code"] == "S" and r["acquired_disposed"] == "D" and r["shares"] == 2398 and r["price"] == 347.56
    assert str(r["transaction_date"]) == "2026-11-24" and r["disclosed_at"].date().isoformat() == "2026-11-25"
    assert r["plan_10b5_1"] is True and "SVP" in r["role"]


def test_insiders_ingest_and_point_in_time_reads():
    conn = duckdb.connect()
    out = own.ingest_insiders(_client("sec_insiders"), "320193", conn)
    assert out["form4_filings_read"] == 3 and out["transactions_added"] >= 3
    assert own.ingest_insiders(_client("sec_insiders"), "320193", conn)["transactions_added"] == 0  # rerun is safe
    before = own.insiders_as_of(conn, datetime(2026, 11, 20, 0, 0, tzinfo=UTC), "AAPL")
    after = own.insiders_as_of(conn, datetime(2026, 11, 26, tzinfo=UTC), "AAPL")
    assert {r["accession"] for r in before} == {"0001140361-26-044952"}  # only what was disclosed by then
    assert len({r["accession"] for r in after}) == 3
    buy = next(r for r in after if r["code"] == "P")
    assert buy["meaning"] == "Open-market purchase" and buy["plan_10b5_1"] is False and buy["disclosure_lag_days"] >= 0
    assert all(r["url"].endswith("form4.xml") and "xsl" not in r["url"] for r in after)


def test_real_13f_sums_rows_per_security_and_keeps_quarter_end_apart_from_filing():
    xml = (FIX / "sec_13f" / "www.sec.gov__Archives__edgar__data__1067983__000119312526463399__60471.xml").read_bytes()
    rows = own.parse_13f(xml)
    ally = [r for r in rows if r["cusip"] == "02005N100"]
    assert len(ally) == 1 and ally[0]["shares"] >= 12561737 + 2803875 + 4228200  # several manager rows summed
    conn = duckdb.connect()
    out = own.ingest_13f(_client("sec_13f"), "1067983", conn)
    assert out["status"] == "OK" and out["period_end"] == "2026-09-30" and out["holdings"] == len(rows)
    assert own.holdings_as_of(conn, datetime(2026, 11, 16, 20, 0, tzinfo=UTC)) == []  # not yet disclosed
    held = own.holdings_as_of(conn, datetime(2026, 11, 17, tzinfo=UTC))
    assert held[0]["period_end"] == "2026-09-30" and held[0]["disclosed_at"].startswith("2026-11-16")
    assert held[0]["value_usd"] >= held[-1]["value_usd"]
