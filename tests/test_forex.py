"""Forex: the OANDA practice client, candles, spreads, risk checks and the simulator.

Candle and price values are invented test numbers in OANDA's documented shape.
"""
from datetime import datetime, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.core.licenses import LicenseNotPermittedError, Permission, load_licenses
from candleisgreen.markets.forex import (ForexSimulator, check_order, notional_usd, pip_size, spread_model, spread_pips,
                                         usd_per_quote)
from candleisgreen.sources.oanda import (LiveHostRefusedError, MissingCredentialsError, OandaPractice, assert_practice,
                                        candle_end, to_bars, transport_from_env)

CFG = load_config()
FX = CFG.assets.forex
NOW = datetime(2026, 11, 27, 15, tzinfo=timezone.utc)


def permitted():
    reg = load_licenses()
    lic = reg.licenses["oanda_practice"].model_copy(update={"research": Permission.PERMITTED})
    return reg.model_copy(update={"licenses": {**reg.licenses, "oanda_practice": lic}})


def candle(t, mid, spread=0.0001, complete=True):
    f = lambda x: f"{x:.5f}"  # noqa: E731
    return {"time": t, "volume": 1000, "complete": complete,
            "mid": {"o": f(mid), "h": f(mid + .002), "l": f(mid - .002), "c": f(mid)},
            "bid": {"o": f(mid - spread / 2), "h": f(mid), "l": f(mid), "c": f(mid - spread / 2)},
            "ask": {"o": f(mid + spread / 2), "h": f(mid), "l": f(mid), "c": f(mid + spread / 2)}}


class Stub:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, base, path, params):
        self.calls.append((base, path, params))
        return self.pages.pop(0)


def test_only_the_practice_host_and_separate_credentials(monkeypatch):
    assert_practice("https://api-fxpractice.oanda.com")
    with pytest.raises(LiveHostRefusedError):
        assert_practice("https://api-fxtrade.oanda.com")
    monkeypatch.delenv("OANDA_PRACTICE_TOKEN", raising=False)
    monkeypatch.setenv("APCA_API_KEY_ID", "alpaca-key-is-not-used-here")
    with pytest.raises(MissingCredentialsError):
        transport_from_env(FX)
    monkeypatch.setenv("OANDA_PRACTICE_TOKEN", "t")
    monkeypatch.setenv("OANDA_PRACTICE_ACCOUNT_ID", "101-001-1-001")
    t, acct = transport_from_env(FX)
    assert t.headers["Authorization"] == "Bearer t" and acct == "101-001-1-001"


def test_client_refuses_until_the_license_is_confirmed_and_has_no_order_methods():
    with pytest.raises(LicenseNotPermittedError):
        OandaPractice(Stub([]), "acct", FX)
    api = OandaPractice(Stub([]), "acct", FX, licenses=permitted())
    assert not any(name in dir(api) for name in ("order", "submit", "send", "orders"))


def test_candles_page_by_the_documented_maximum_and_keep_bid_and_ask():
    small = FX.model_copy(update={"max_candles_per_request": 2})
    t = Stub([{"candles": [candle("2026-11-23T22:00:00.000000000Z", 1.05), candle("2026-11-24T22:00:00.000000000Z", 1.06)]},
              {"candles": [candle("2026-11-25T22:00:00.000000000Z", 1.07, complete=False)]}])
    api = OandaPractice(t, "acct", small, licenses=permitted())
    rows = api.candles("EUR_USD", datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert len(rows) == 3 and t.calls[0][2]["price"] == "MBA" and t.calls[0][1] == "/v3/accounts/acct/instruments/EUR_USD/candles"
    bars = to_bars("EUR_USD", rows, "D", FX)
    assert bars[0].bid_close == pytest.approx(1.04995) and bars[0].ask_close == pytest.approx(1.05005)
    assert [b.complete for b in bars] == [True, True, False]


def test_daily_candles_end_at_five_pm_new_york_across_daylight_saving():
    winter = candle_end(datetime(2026, 11, 23, 22, tzinfo=timezone.utc), "D", FX)
    assert winter == datetime(2026, 11, 24, 22, tzinfo=timezone.utc)
    summer = candle_end(datetime(2026, 7, 13, 21, tzinfo=timezone.utc), "D", FX)
    assert summer == datetime(2026, 7, 14, 21, tzinfo=timezone.utc)


def test_pips_spreads_and_conversion():
    assert pip_size(-4) == 0.0001 and pip_size(-2) == 0.01
    assert spread_pips(1.1000, 1.1002, 0.0001) == pytest.approx(2)
    bars = to_bars("EUR_USD", [candle(f"2026-11-{d:02d}T22:00:00Z", 1.05, spread=0.0001 * (1 + d % 3)) for d in range(1, 21)], "D", FX)
    m = spread_model("EUR_USD", bars, 0.0001)
    assert m.observations == 20 and m.median_pips == pytest.approx(2, abs=1e-6) and m.p90_pips == pytest.approx(3, abs=1e-6)
    mids = {"EUR_USD": 1.10, "USD_JPY": 150.0}
    assert usd_per_quote("USD_JPY", 150.0, mids) == pytest.approx(1 / 150)
    assert notional_usd("EUR_USD", 10_000, 1.10, mids) == pytest.approx(11_000)
    assert notional_usd("USD_JPY", -10_000, 150.0, mids) == 10_000


def names(checks):
    return {c.name for c in checks if not c.passed}


def test_risk_checks_cap_size_leverage_and_spread():
    mids = {"EUR_USD": 1.10}
    assert names(check_order("EUR_USD", 5_000, 1.0999, 1.1001, 1e-4, 100_000, 0, mids, FX)) == set()
    assert "position" in names(check_order("EUR_USD", 50_000, 1.0999, 1.1001, 1e-4, 100_000, 0, mids, FX))
    assert "leverage" in names(check_order("EUR_USD", 5_000, 1.0999, 1.1001, 1e-4, 100_000, 99_000, mids, FX))
    assert "spread" in names(check_order("EUR_USD", 5_000, 1.0990, 1.1010, 1e-4, 100_000, 0, mids, FX))
    assert "listed" in names(check_order("EUR_TRY", 5_000, 1.0999, 1.1001, 1e-4, 100_000, 0, mids, FX))


def test_simulator_fills_at_bid_and_ask_realizes_profit_and_flips():
    sim = ForexSimulator(FX, cash_usd=100_000)
    mids = {"EUR_USD": 1.10}
    st, _, f = sim.order("EUR_USD", 5_000, 1.0999, 1.1001, 1e-4, NOW, mids)
    assert st == "filled" and f.price == 1.1001 and "financing is not included" in f.label
    mids = {"EUR_USD": 1.12}
    st, _, f = sim.order("EUR_USD", -5_000, 1.1199, 1.1201, 1e-4, NOW, mids)
    assert sim.cash_usd == pytest.approx(100_000 + 5_000 * (1.1199 - 1.1001)) and "EUR_USD" not in sim.positions
    st, checks, _ = sim.order("EUR_USD", 90_000, 1.1199, 1.1201, 1e-4, NOW, mids)
    assert st == "blocked" and "position" in names(checks)
    sim.order("EUR_USD", 2_000, 1.1199, 1.1201, 1e-4, NOW, mids)
    sim.order("EUR_USD", -3_000, 1.1199, 1.1201, 1e-4, NOW, mids)
    assert sim.positions["EUR_USD"] == (-1_000, 1.1199)
