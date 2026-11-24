"""Execution quotes from Alpaca's free IEX real-time feed and the paper trading clock.

`GET /v2/stocks/quotes/latest?symbols=...&feed=iex` on the market data host and `GET /v2/clock` on
the paper trading host (Alpaca API reference, read 2026-11-24). A price of 0 means no active bid or
ask, and such a side gives no quote. Halts are read as an asset that is not tradable or not listed
as active. Anything that cannot be read is None, and the risk service then blocks the order.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ..core.config import AlpacaSourceConfig
from ..core.schemas import Quote
from ..core.timeutil import ensure_utc
from .alpaca import ASSETS_PATH

QUOTES_PATH = "/v2/stocks/quotes/latest"
CLOCK_PATH = "/v2/clock"
FEED = "iex"
FEED_LABEL = "iex_realtime"


def parse_time(text: str) -> datetime:
    """RFC 3339 with up to nanoseconds. Python keeps microseconds."""
    head, _, rest = text.replace("Z", "+00:00").partition(".")
    if not rest:
        return ensure_utc(datetime.fromisoformat(head))
    n = 0
    while n < len(rest) and rest[n].isdigit():
        n += 1
    digits, tz = rest[:n], rest[n:] or "+00:00"
    return ensure_utc(datetime.fromisoformat(f"{head}.{digits[:6].ljust(6, '0')}{tz}"))


class AlpacaQuotes:
    def __init__(self, transport: Any, cfg: AlpacaSourceConfig):
        self.t = transport
        self.cfg = cfg
        self._clock: Optional[dict] = None
        self._assets: Optional[dict[str, dict]] = None

    def _is_open(self) -> Optional[bool]:
        if self._clock is None:
            try:
                self._clock = self.t.get(self.cfg.trading_base_url, CLOCK_PATH, {})
            except Exception:
                return None
        v = self._clock.get("is_open")
        return v if isinstance(v, bool) else None

    def _halted(self, symbol: str) -> Optional[bool]:
        if self._assets is None:
            try:
                self._assets = {a["symbol"]: a for a in self.t.get(self.cfg.trading_base_url, ASSETS_PATH,
                                                                     {"status": "active", "asset_class": "us_equity"})}
            except Exception:
                return None
        a = self._assets.get(symbol)
        return True if a is None else not bool(a.get("tradable", False))

    def snapshot(self, symbol: str, instrument_id: str, now: datetime):
        from ..trading import MarketSnapshot

        quote = None
        try:
            data = self.t.get(self.cfg.data_base_url, QUOTES_PATH, {"symbols": symbol, "feed": FEED})
            q = (data.get("quotes") or {}).get(symbol)
            if q and q.get("ap", 0) > 0 and q.get("bp", 0) > 0:
                quote = Quote(asset_id=instrument_id, bid=float(q["bp"]), ask=float(q["ap"]),
                              quote_time=parse_time(q["t"]), feed=FEED_LABEL)
        except Exception:
            quote = None
        return MarketSnapshot(quote, self._is_open(), self._halted(symbol))
