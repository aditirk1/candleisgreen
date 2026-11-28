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

pytestmark = pytest.mark.skipif(os.environ.get("CANDLE_LIVE") != "1", reason="live source checks run only with CANDLE_LIVE=1")
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
