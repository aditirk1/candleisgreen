"""Crypto: store, Alpaca and Kraken parsing, fees, book quality, risk checks and the simulator.

Book and bar values are invented test numbers in the documented response shape.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.core.licenses import LicenseNotPermittedError
from candleisgreen.markets.crypto import CryptoSimulator, book_quality, check_order, fee_bps, series_stats, walk_book
from candleisgreen.markets.store import MarketStore
from candleisgreen.sources.alpaca_crypto import AlpacaCrypto, to_bars
from candleisgreen.sources.kraken import KrakenPublic, parse_ohlc, parse_ticker
from candleisgreen.sources.public_http import HostNotAllowedError, PublicTransport

CFG = load_config()
CR = CFG.assets.crypto
NOW = datetime(2026, 11, 28, 2, 30, tzinfo=timezone.utc)
BOOK = {"t": "2026-11-28T02:27:39Z",
        "b": [{"p": 60000.0, "s": 0.05}, {"p": 59990.0, "s": 0.2}, {"p": 59000.0, "s": 5}],
        "a": [{"p": 60010.0, "s": 0.05}, {"p": 60020.0, "s": 0.2}, {"p": 61000.0, "s": 5}]}


def bar_rows(n, start=date(2026, 10, 1)):
    return [{"t": f"{start + timedelta(days=i)}T00:00:00Z", "o": 100 + i, "h": 102 + i, "l": 99 + i, "c": 101 + i, "v": 2.0, "n": 10, "vw": 100.5 + i}
            for i in range(n)]


def test_daily_bars_are_usable_only_after_they_close_and_never_stored_open():
    rows = bar_rows(2, date(2026, 11, 26)) + [{"t": "2026-11-28T00:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]
    bars = to_bars("BTC/USD", rows, NOW)
    assert [b.complete for b in bars] == [True, True, False]
    assert bars[0].first_usable_at == datetime(2026, 11, 27, tzinfo=timezone.utc)


def test_store_keeps_vintages_and_reads_point_in_time(tmp_path):
    s = MarketStore(tmp_path / "m.sqlite", shared=False)
    bars = to_bars("BTC/USD", bar_rows(3, date(2026, 11, 24)), NOW)
    assert s.add_bars(bars, NOW) == 3 and s.add_bars(bars, NOW) == 0
    assert len(s.bars("alpaca_us", "BTC/USD", "1Day", datetime(2026, 11, 26, 0, 0, 1, tzinfo=timezone.utc))) == 2
    revised = [b.__class__(**{**b.__dict__, "close": 999.0}) for b in bars[:1]]
    later = NOW + timedelta(hours=5)
    assert s.add_bars(revised, later) == 1
    assert s.bars("alpaca_us", "BTC/USD", "1Day", NOW)[0].close == 101
    assert s.bars("alpaca_us", "BTC/USD", "1Day", later + timedelta(seconds=1))[0].close == 999.0
    assert s.symbols("crypto")[0][:3] == ("alpaca_us", "BTC/USD", 3)


class Stub:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, base, path, params):
        self.calls.append((base, path, params))
        return self.pages.pop(0)


def test_alpaca_crypto_client_pages_and_clamps_to_the_history_start():
    t = Stub([{"bars": {"BTC/USD": bar_rows(2)}, "next_page_token": "x"}, {"bars": {"BTC/USD": bar_rows(1, date(2026, 10, 3))}, "next_page_token": None}])
    out = AlpacaCrypto(t, CFG.sources.alpaca, CR).daily_bars(["BTC/USD"], date(2015, 1, 1))
    assert len(out["BTC/USD"]) == 3 and t.calls[0][1] == "/v1beta3/crypto/us/bars"
    assert t.calls[0][2]["start"] == "2021-01-01" and t.calls[1][2]["page_token"] == "x"


def test_fees_follow_the_published_tiers():
    assert fee_bps(CR, 0, maker=False) == 25 and fee_bps(CR, 0, maker=True) == 15
    assert fee_bps(CR, 150_000, maker=False) == 22 and fee_bps(CR, 2e8, maker=True) == 0


def test_book_quality_and_walking_the_book():
    q = book_quality(BOOK, CR)
    assert q.mid == pytest.approx(60005) and q.spread_bps == pytest.approx(10 / 60005 * 1e4)
    assert q.ask_depth_usd == pytest.approx(60010 * .05 + 60020 * .2)
    price, qty = walk_book(BOOK["a"], 6000)
    assert price == pytest.approx(60014.0, rel=1e-4) and qty * price == pytest.approx(6000)
    assert walk_book(BOOK["a"], 10_000_000) is None
    assert book_quality({"b": [{"p": 2, "s": 1}], "a": [{"p": 1, "s": 1}]}, CR) is None


def names(checks):
    return {c.name for c in checks if not c.passed}


def test_risk_checks_forbid_shorts_and_cap_size_spread_and_depth():
    q = book_quality(BOOK, CR)
    assert names(check_order("buy", 1000, "BTC/USD", q, CR, equity=100_000, held_value=0, total_crypto_value=0)) == set()
    assert "no_short" in names(check_order("sell", 1000, "BTC/USD", q, CR, 100_000, held_value=500, total_crypto_value=500))
    assert "position" in names(check_order("buy", 2500, "BTC/USD", q, CR, 100_000, 0, 0))
    assert "total" in names(check_order("buy", 1000, "BTC/USD", q, CR, 100_000, 0, 4500))
    assert "listed" in names(check_order("buy", 100, "DOGE/USD", q, CR, 100_000, 0, 0))
    assert "order_size" in names(check_order("buy", 250_000, "BTC/USD", q, CR, 1e9, 0, 0))
    wide = book_quality({"b": [{"p": 59000, "s": 1}], "a": [{"p": 61000, "s": 1}]}, CR)
    assert {"spread", "depth"} <= names(check_order("buy", 1000, "BTC/USD", wide, CR, 1e6, 0, 0))
    assert "book" in names(check_order("buy", 1000, "BTC/USD", None, CR, 1e6, 0, 0))


def test_simulator_charges_the_taker_fee_in_what_is_received_and_never_goes_short():
    sim = CryptoSimulator(CR, cash=100_000)
    status, _, fill = sim.order("buy", "BTC/USD", 1500, BOOK, NOW, equity=100_000, mids={"BTC/USD": 60005})
    assert status == "filled" and fill.fee_usd == pytest.approx(1500 * 25 / 1e4)
    assert sim.cash == pytest.approx(98_500)
    assert sim.holdings["BTC/USD"] == pytest.approx(fill.quantity * (1 - 0.0025))
    status, checks, _ = sim.order("sell", "BTC/USD", 5000, BOOK, NOW, 100_000, {"BTC/USD": 60005})
    assert status == "blocked" and "no_short" in names(checks)
    poor = CryptoSimulator(CR, cash=100)
    assert "cash" in names(poor.order("buy", "BTC/USD", 500, BOOK, NOW, 100_000, {})[1])


def test_series_stats_use_calendar_days():
    bars = to_bars("BTC/USD", bar_rows(40), NOW)
    st = series_stats(bars)
    assert st.days == 40 and st.total_return == pytest.approx(140 / 101 - 1) and st.max_drawdown == 0
    assert st.annual_volatility is not None and st.median_daily_volume == 2.0


KRAKEN_OHLC = {"error": [], "result": {"XXBTZUSD": [[1795564800, "60000.0", "61000.0", "59000.0", "60500.0", "60200.0", "100.5", 900],
                                                   [1795651200, "60500.0", "60600.0", "60000.0", "60100.0", "60300.0", "10.0", 90]],
                                      "last": 1795564800}}


def test_kraken_parsing_and_its_license_gate():
    bars = parse_ohlc(KRAKEN_OHLC, "BTC/USD", datetime(2026, 11, 27, 12, tzinfo=timezone.utc))
    assert [b.complete for b in bars] == [True, False] and bars[0].volume == 100.5 and bars[0].vwap == 60200.0
    assert parse_ticker({"error": [], "result": {"XXBTZUSD": {"a": ["60113.9", "2", "2.0"], "b": ["60113.8", "1", "1.0"], "c": ["60113.9", "0.1"]}}}) \
        == {"XXBTZUSD": {"ask": 60113.9, "bid": 60113.8, "last": 60113.9}}
    with pytest.raises(LicenseNotPermittedError):
        KrakenPublic(Stub([]))


def test_public_transport_refuses_hosts_outside_the_allowlist():
    with pytest.raises(HostNotAllowedError):
        PublicTransport().get("https://api.alpaca.markets", "/v2/orders", {})
    with pytest.raises(HostNotAllowedError):
        PublicTransport().get("https://paper-api.alpaca.markets", "/v2/account", {})
