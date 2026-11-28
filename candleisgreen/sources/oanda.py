"""OANDA v20 practice API, read only.

Practice host only (api-fxpractice.oanda.com). The live host is refused. Credentials are kept
apart from Alpaca: OANDA_PRACTICE_TOKEN and OANDA_PRACTICE_ACCOUNT_ID, from the environment only.
This client has no order methods.

Endpoints and fields follow OANDA's documentation as read on 2026-11-28:
- GET /v3/accounts/{id}/instruments: name, type, pipLocation, marginRate, minimumTradeSize.
- GET /v3/accounts/{id}/instruments/{instrument}/candles: price M, B, A. count at most 5000.
  Each candle has time, volume (number of prices), complete, and mid, bid, ask with o h l c strings.
- GET /v3/accounts/{id}/pricing: bids and asks per instrument.
Not yet checked against a live response, because no practice token exists in the build
environment. OANDA's API license text could not be read, so the license `oanda_practice` is
unverified and the client refuses to fetch until it is marked permitted.

OANDA's prices and spreads are OANDA's own. They are not a view of the whole currency market.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..core.config import ForexConfig
from ..core.licenses import LicenseRegistry, load_licenses
from ..core.timeutil import ensure_utc, iso_utc, parse_rfc3339
from ..markets.store import Bar
from .public_http import PublicTransport

LICENSE = "oanda_practice"
VENDOR = "oanda_practice"
PRACTICE_HOST = "api-fxpractice.oanda.com"
GRANULARITY = {"D": timedelta(days=1), "H1": timedelta(hours=1), "H4": timedelta(hours=4), "M15": timedelta(minutes=15)}


class MissingCredentialsError(RuntimeError):
    pass


class LiveHostRefusedError(RuntimeError):
    pass


def assert_practice(url: str) -> None:
    if (urlparse(url).hostname or "").lower() != PRACTICE_HOST:
        raise LiveHostRefusedError("only the OANDA practice host is allowed")


def transport_from_env(cfg: ForexConfig, timeout: float = 30) -> tuple[PublicTransport, str]:
    token, account = os.environ.get("OANDA_PRACTICE_TOKEN"), os.environ.get("OANDA_PRACTICE_ACCOUNT_ID")
    if not token or not account:
        raise MissingCredentialsError("set OANDA_PRACTICE_TOKEN and OANDA_PRACTICE_ACCOUNT_ID for an fxTrade Practice account")
    return PublicTransport(timeout, 3, {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}), account


def candle_end(start: datetime, granularity: str, cfg: ForexConfig) -> datetime:
    """A daily candle ends at the next daily alignment hour in the alignment time zone."""
    if granularity != "D":
        return start + GRANULARITY[granularity]
    tz = ZoneInfo(cfg.alignment_timezone)
    local = ensure_utc(start).astimezone(tz)
    nxt = (local + timedelta(days=1)).replace(hour=cfg.daily_alignment_hour, minute=0, second=0, microsecond=0)
    return nxt.astimezone(ZoneInfo("UTC"))


def to_bars(instrument: str, candles: list[dict], granularity: str, cfg: ForexConfig) -> list[Bar]:
    out = []
    for c in candles:
        mid, bid, ask = c.get("mid"), c.get("bid"), c.get("ask")
        if not mid:
            continue
        start = parse_rfc3339(c["time"])
        out.append(Bar("fx", "oanda_practice", instrument, granularity, start, float(mid["o"]), float(mid["h"]), float(mid["l"]),
                       float(mid["c"]), float(c.get("volume") or 0), bool(c.get("complete")), VENDOR, LICENSE,
                       candle_end(start, granularity, cfg), bid_close=float(bid["c"]) if bid else None,
                       ask_close=float(ask["c"]) if ask else None))
    return out


class OandaPractice:
    def __init__(self, transport, account_id: str, cfg: ForexConfig, licenses: Optional[LicenseRegistry] = None):
        assert_practice(cfg.practice_rest_url)
        (licenses or load_licenses()).assert_use([LICENSE], "research")
        self.t, self.account, self.cfg = transport, account_id, cfg

    def _get(self, path: str, params: dict) -> dict:
        return self.t.get(self.cfg.practice_rest_url, f"/v3/accounts/{self.account}{path}", params)

    def instruments(self) -> list[dict]:
        return self._get("/instruments", {"instruments": ",".join(self.cfg.instruments)}).get("instruments") or []

    def candles(self, instrument: str, start: datetime, granularity: Optional[str] = None) -> list[dict]:
        """Bid, ask and mid candles from `start`, paged by the documented maximum count."""
        g = granularity or self.cfg.granularity
        out: list[dict] = []
        cursor = ensure_utc(start)
        while True:
            page = self._get(f"/instruments/{instrument}/candles", {
                "price": "MBA", "granularity": g, "from": iso_utc(cursor), "count": self.cfg.max_candles_per_request,
                "dailyAlignment": self.cfg.daily_alignment_hour, "alignmentTimezone": self.cfg.alignment_timezone})
            rows = page.get("candles") or []
            new = [r for r in rows if not out or parse_rfc3339(r["time"]) > parse_rfc3339(out[-1]["time"])]
            out.extend(new)
            if len(rows) < self.cfg.max_candles_per_request or not new:
                return out
            cursor = parse_rfc3339(rows[-1]["time"]) + timedelta(seconds=1)

    def pricing(self) -> dict[str, dict]:
        page = self._get("/pricing", {"instruments": ",".join(self.cfg.instruments)})
        out = {}
        for p in page.get("prices") or []:
            bids, asks = p.get("bids") or [], p.get("asks") or []
            if bids and asks:
                out[p["instrument"]] = {"bid": float(bids[0]["price"]), "ask": float(asks[0]["price"]), "time": p.get("time"),
                                        "tradeable": p.get("tradeable", p.get("status") == "tradeable")}
        return out
