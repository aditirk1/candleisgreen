"""Futures: contract calendar, rolls, continuous series, the daily simulator and CFTC positioning.

COT fixtures are real CFTC reports (public domain). Settlement prices are invented test numbers.
"""
import json
from datetime import date, datetime, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.markets.futures import (CalendarGapError, FuturesSimulator, UnknownContractError, continuous, contract_code,
                                           first_notice_day, front_contract, last_trade_day, parse_code, parse_settlements,
                                           products, roll_date)
from candleisgreen.sources.cftc import DATASETS, fetch, first_usable_at, percentile, positioning, report_date
from tests.phase1_env import ROOT

CFG = load_config()
FU = CFG.assets.futures
FIX = ROOT / "tests" / "fixtures" / "cftc"


def test_every_product_is_marked_unverified_until_checked_against_cme():
    assert set(products()) == {"ES", "NQ", "CL", "GC", "ZN"}
    assert all(not p.verified and not p.calendar_checked and p.source.startswith("https://www.cmegroup.com/") for p in products().values())


FIXTURE_OF = {"ES": "tff_es", "NQ": "tff_nq", "CL": "disagg_cl", "GC": "legacy_gc", "ZN": "tff_zn"}


@pytest.mark.recorded
def test_every_contract_size_matches_the_cftcs_own_record():
    from candleisgreen.markets.futures import cftc_size, multiplier_confirmed, term_status
    assert cftc_size("($50 X S&P 500 INDEX)") == 50 and cftc_size("(NASDAQ 100 STOCK INDEX X $20)") == 20
    assert cftc_size("(CONTRACTS OF 1,000 BARRELS)") == 1000 and cftc_size("(CONTRACTS OF $100,000 FACE VALUE)") == 100_000
    for code, fx in FIXTURE_OF.items():
        units = json.loads((FIX / f"{fx}.json").read_text())[0]["contract_units"]
        terms = {t.field: t.status for t in term_status(code, units)}
        assert terms["multiplier"] == "cross_checked", code
        assert terms["tick_size"] == terms["last_trade_rule"] == "estimated"
        assert multiplier_confirmed(code, units)
    assert not multiplier_confirmed("ES", "($20 X S&P 500 INDEX)")                # a wrong size is caught
    assert not multiplier_confirmed("ES", None)                                     # no record, no confirmation


@pytest.mark.recorded
def test_cftc_rows_are_validated_before_storage():
    from candleisgreen.sources.cftc import InvalidReportError, validate
    row = json.loads((FIX / "tff_es.json").read_text())[0]
    assert validate(row, "tff", "13874A") == date(2026, 11, 17)
    for bad, why in [({**row, "cftc_contract_market_code": "209742"}, "market"), ({**row, "futonly_or_combined": "Combined"}, "futures-only"),
                     ({**row, "report_date_as_yyyy_mm_dd": "2026-11-18T00:00:00.000"}, "Tuesday"), ({**row, "open_interest_all": "-1"}, "negative"),
                     ({k: v for k, v in row.items() if k != "asset_mgr_positions_long"}, "missing")]:
        with pytest.raises(InvalidReportError, match=why):
            validate(bad, "tff", "13874A")


def test_contract_codes_round_trip():
    assert contract_code("ES", 2026, 12) == "ESZ26" and parse_code("esz26") == ("ES", 2026, 12)
    with pytest.raises(UnknownContractError):
        parse_code("XXZ26")


def test_last_trading_days_follow_each_products_rule():
    assert last_trade_day("ES", 2026, 12) == date(2026, 12, 18)        # third Friday
    assert last_trade_day("ES", 2027, 3) == date(2027, 3, 19)
    assert last_trade_day("CL", 2027, 1) == date(2026, 12, 21)         # 25 Dec is a holiday: 4 business days before
    assert last_trade_day("CL", 2026, 12) == date(2026, 11, 20)        # 25 Nov is a business day: 3 before
    assert last_trade_day("GC", 2026, 12) == date(2026, 12, 29)        # third-last business day
    assert first_notice_day("GC", 2026, 12) == date(2026, 11, 30)
    assert last_trade_day("ZN", 2026, 12) == date(2026, 12, 21)        # 7 business days before 31 Dec
    with pytest.raises(CalendarGapError):
        last_trade_day("ES", 2029, 3)


def test_rolls_happen_before_first_notice_for_physical_contracts():
    assert roll_date("GC", 2026, 12, FU) == date(2026, 11, 20)          # 5 business days before 30 Nov, Thanksgiving skipped
    assert front_contract("GC", date(2026, 11, 19), FU)[0] == "GCZ26"
    assert front_contract("GC", date(2026, 11, 20), FU)[0] == "GCG27"
    assert front_contract("ES", date(2026, 12, 14), FU)[0] == "ESH27"


CSV = """date,contract,settle
2026-12-08,ESZ26,6000
2026-12-08,ESH27,6050
2026-12-09,ESZ26,6010
2026-12-09,ESH27,6060
2026-12-10,ESZ26,6020
2026-12-10,ESH27,6070
2026-12-11,ESZ26,6030
2026-12-11,ESH27,6080
2026-12-14,ESH27,6090
"""


def test_continuous_series_adjust_history_at_the_roll():
    series = parse_settlements(CSV)
    assert set(series) == {"ESZ26", "ESH27"}
    pts = continuous("ES", series, FU, "back_adjusted")
    roll = next(p for p in pts if p.rolled)
    assert roll.contract == "ESH27" and roll.day == date(2026, 12, 11)
    assert [p.adjusted for p in pts][:3] == [6050, 6060, 6070]
    assert [p.raw for p in continuous("ES", series, FU, "unadjusted")][:3] == [6000, 6010, 6020]
    ratio = continuous("ES", series, FU, "ratio_adjusted")
    assert ratio[0].adjusted == pytest.approx(6000 * 6080 / 6030)
    with pytest.raises(UnknownContractError):
        parse_settlements("date,contract,settle\n2026-12-08,QQZ26,1\n")


def test_simulator_needs_a_margin_moves_variation_margin_and_closes_on_a_margin_call():
    unconfirmed = FuturesSimulator(FU, cash=400_000)
    st, checks = unconfirmed.trade("ESZ26", 1, 6000, 9_000)
    assert st == "blocked" and any(c.name == "multiplier_confirmed" and not c.passed for c in checks)
    sim = FuturesSimulator(FU, cash=100_000, confirmed=frozenset({"ES"}))
    st, checks = sim.trade("ESZ26", 1, 6000, None)
    assert st == "blocked" and any(c.name == "margin_known" and not c.passed for c in checks)
    st, _ = sim.trade("ESZ26", 1, 6000, 25_000)
    assert st == "blocked"  # 25 000 margin is over 10% of the account
    st, _ = sim.trade("ESZ26", 1, 6000, 9_000)
    assert st == "blocked"  # contract value 300 000 is over the account
    big = FuturesSimulator(FU, cash=400_000, confirmed=frozenset({"ES"}))
    assert big.trade("ESZ26", 1, 6000, 9_000)[0] == "filled"
    big.mark(date(2026, 12, 9), {"ESZ26": 5990}, {"ESZ26": 8_000})
    assert big.cash == pytest.approx(400_000 - 500)
    notes = big.mark(date(2026, 12, 10), {}, {"ESZ26": 8_000})
    assert "not marked" in notes[0]
    big.cash = 7_000
    notes = big.mark(date(2026, 12, 11), {"ESZ26": 5990}, {"ESZ26": 8_000})
    assert "maintenance margin" in notes[0] and not big.positions


@pytest.mark.recorded
def test_cot_reports_count_only_once_surely_public():
    rows = json.loads((FIX / "tff_es.json").read_text())
    rep = report_date(rows[0])
    assert rep == date(2026, 11, 17) and rep.weekday() == 1
    friday = datetime(2026, 11, 20, 20, 30, tzinfo=timezone.utc)      # 15:30 ET
    assert first_usable_at(rep, datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc), FU) == datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)
    assert first_usable_at(rep, datetime(2026, 11, 18, tzinfo=timezone.utc), FU) == friday
    assert first_usable_at(rep, datetime(2026, 11, 28, tzinfo=timezone.utc), FU) == datetime(2026, 11, 23, 20, 30, tzinfo=timezone.utc)


@pytest.mark.recorded
def test_cot_positioning_on_real_reports():
    es = json.loads((FIX / "tff_es.json").read_text())[0]
    oi, groups = positioning(es, "tff")
    assert oi == 2_096_958
    am = groups[0]
    assert (am.label, am.long, am.short, am.net) == ("Asset managers", 1_122_337, 227_288, 895_049)
    cl = json.loads((FIX / "disagg_cl.json").read_text())[0]
    assert positioning(cl, "disaggregated")[1][2].short == 601_471      # swap dealers use the CFTC's double underscore field
    gc = json.loads((FIX / "legacy_gc.json").read_text())[0]
    assert positioning(gc, "legacy")[1][0].net == 210_051 - 43_919
    assert percentile([1.0] * 10, 1.0) is None and percentile(list(range(100)), 49) == pytest.approx(0.5)


def test_cot_fetch_builds_the_documented_query():
    class Stub:
        def get(self, base, path, params):
            self.call = (base, path, params)
            return []
    s = Stub()
    fetch(s, "tff", "13874A", since=date(2026, 1, 1))
    assert s.call[0] == "https://publicreporting.cftc.gov" and s.call[1] == f"/resource/{DATASETS['tff']}.json"
    assert "13874A" in s.call[2]["$where"] and "2026-01-01" in s.call[2]["$where"]
