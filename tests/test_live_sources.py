"""Read-only checks against the real sources. Skipped unless CANDLE_LIVE=1.

Run:  CANDLE_LIVE=1 .venv/bin/python -m pytest tests/test_live_sources.py -v
Crypto and CFTC need no key. Options need APCA_API_KEY_ID and APCA_API_SECRET_KEY (paper).
Forex needs OANDA_PRACTICE_TOKEN, OANDA_PRACTICE_ACCOUNT_ID and the oanda_practice license
marked permitted. Nothing here places an order.
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from candleisgreen.core.config import load_config

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("CANDLE_LIVE") != "1", reason="live source checks run only with CANDLE_LIVE=1")]
CFG = load_config()
NOW = datetime.now(timezone.utc)


def test_alpaca_crypto_history_and_current_book():
    from candleisgreen.markets.crypto import book_quality
    from candleisgreen.sources.alpaca_crypto import AlpacaCrypto, to_bars, transport_from_env
    api = AlpacaCrypto(transport_from_env(CFG.sources.alpaca), CFG.sources.alpaca, CFG.assets.crypto)
    rows = api.daily_bars(["BTC/USD"], CFG.assets.crypto.history_start, date(2021, 1, 10))["BTC/USD"]
    assert rows[0]["t"].startswith(CFG.assets.crypto.history_start.isoformat())
    bars = to_bars("BTC/USD", rows, NOW)
    assert all(b.complete and b.high >= b.low for b in bars)
    book = api.latest_orderbooks(["BTC/USD"])["BTC/USD"]
    q = book_quality(book, CFG.assets.crypto)
    assert q is not None and q.spread_bps > 0
    from candleisgreen.core.timeutil import parse_rfc3339
    assert NOW - parse_rfc3339(book["t"]) < timedelta(hours=1)


def test_alpaca_crypto_response_fields_match_what_the_parsers_and_fixtures_assume():
    """The documented-shape tests use invented values. This checks the real field names behind them."""
    from candleisgreen.sources.alpaca_crypto import AlpacaCrypto, transport_from_env
    api = AlpacaCrypto(transport_from_env(CFG.sources.alpaca), CFG.sources.alpaca, CFG.assets.crypto)
    bar = api.daily_bars(["BTC/USD"], date(2024, 1, 1), date(2024, 1, 2))["BTC/USD"][0]
    assert {"t", "o", "h", "l", "c", "v", "n", "vw"} <= set(bar)
    book = api.latest_orderbooks(["BTC/USD"])["BTC/USD"]
    assert {"t", "b", "a"} <= set(book) and {"p", "s"} <= set(book["b"][0])
    quote = api.latest_quotes(["BTC/USD"])["BTC/USD"]
    assert {"t", "bp", "ap", "bs", "as"} <= set(quote)
    trades = api.trades("BTC/USD", NOW - timedelta(hours=6), limit=5)
    assert trades and {"t", "p", "s"} <= set(trades[0])


def test_live_crypto_practice_order_end_to_end(tmp_path):
    """A practice order through the real API route against the live Alpaca book. No broker order exists."""
    from fastapi.testclient import TestClient
    from candleisgreen.api.app import create_app
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", CFG))
    book = api.get("/api/assets/crypto/book", params={"symbol": "BTC/USD"}).json()
    assert book["status"] == "OK" and book["fresh"], book
    out = api.post("/api/assets/crypto/simulate", json={"client_order_id": "live-1", "side": "buy", "symbol": "BTC/USD", "notional": 100}).json()
    times = [c for c in out["checks"] if c["name"] == "book_time"]
    assert times and times[0]["passed"], out["checks"]
    again = api.post("/api/assets/crypto/simulate", json={"client_order_id": "live-1", "side": "buy", "symbol": "BTC/USD", "notional": 100}).json()
    assert again["duplicate"] and again["cash"] == out["cash"]


def test_cftc_recording_validates_every_product_and_confirms_contract_sizes(tmp_path):
    from candleisgreen.markets.futures import multiplier_confirmed, products
    from candleisgreen.markets.service import record_cot
    from candleisgreen.markets.store import MarketStore
    from candleisgreen.sources.public_http import PublicTransport
    store = MarketStore(tmp_path / "m.sqlite", shared=False)
    out = record_cot(store, PublicTransport(), CFG, NOW, since=NOW.date() - timedelta(weeks=6))
    assert not out["rejected"] and all(n >= 4 for n in out["stored"].values()), out
    for code, p in products().items():
        latest = store.reports(p.cot_dataset, p.cftc_code, NOW + timedelta(days=30))[-1][1]
        assert multiplier_confirmed(code, latest["contract_units"]), (code, latest["contract_units"])


def test_kraken_is_not_called_while_its_license_is_unconfirmed():
    from candleisgreen.core.licenses import LicenseNotPermittedError
    from candleisgreen.sources.kraken import KrakenPublic
    from candleisgreen.sources.public_http import PublicTransport
    with pytest.raises(LicenseNotPermittedError):
        KrakenPublic(PublicTransport())


def test_cftc_cot_latest_report_parses():
    from candleisgreen.sources.cftc import fetch, positioning
    from candleisgreen.sources.public_http import PublicTransport
    rows = fetch(PublicTransport(), "tff", "13874A", limit=2)
    oi, groups = positioning(rows[0], "tff")
    assert oi > 0 and groups[0].label == "Asset managers"


@pytest.mark.skipif(not os.environ.get("APCA_API_KEY_ID"), reason="needs Alpaca paper keys")
def test_alpaca_options_contracts_and_indicative_chain():
    from candleisgreen.sources.alpaca import HttpTransport
    from candleisgreen.sources.alpaca_options import AlpacaOptions
    api = AlpacaOptions(HttpTransport(CFG.sources.alpaca), CFG.sources.alpaca, CFG.assets.options)
    today = NOW.date()
    contracts = api.contracts("SPY", today, today + timedelta(days=21))
    assert contracts and all(c.contract.multiplier == 100 for c in contracts)
    chain = api.chain("SPY", today, today + timedelta(days=21))
    assert chain and all(q.feed == "indicative" and not q.executable for q in chain.values())


@pytest.mark.skipif(not os.environ.get("OANDA_PRACTICE_TOKEN"), reason="needs an OANDA practice token")
def test_oanda_practice_candles_and_prices():
    from candleisgreen.sources.oanda import OandaPractice, to_bars, transport_from_env
    t, acct = transport_from_env(CFG.assets.forex)
    api = OandaPractice(t, acct, CFG.assets.forex)
    rows = api.candles("EUR_USD", NOW - timedelta(days=20))
    bars = to_bars("EUR_USD", rows, "D", CFG.assets.forex)
    assert bars and all(b.bid_close < b.ask_close for b in bars)
    assert "EUR_USD" in api.pricing()
