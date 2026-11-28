"""Alpaca crypto market data, read only.

Checked live on 2026-11-28 without keys: bars, latest quotes, latest order books, trades and
snapshots under data.alpaca.markets/v1beta3/crypto/us all answered. Daily bars start at
00:00 UTC, and BTC/USD history starts 2021-01-01. Alpaca's documentation shows the same calls
with key headers, so keys are sent when APCA_API_KEY_ID and APCA_API_SECRET_KEY are set.

The "us" location is Alpaca's own book. Its volume is Alpaca's volume, not the whole market.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from ..core.config import AlpacaSourceConfig, CryptoConfig
from ..core.timeutil import ensure_utc, iso_utc, parse_rfc3339
from ..markets.store import Bar
from .public_http import PublicTransport

VENDOR = "alpaca_crypto"
LICENSE = "alpaca_market_data"


def transport_from_env(cfg: AlpacaSourceConfig) -> PublicTransport:
    key, secret = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret} if key and secret else {}
    return PublicTransport(cfg.request_timeout_seconds, cfg.max_retries, headers)


class AlpacaCrypto:
    def __init__(self, transport, alpaca: AlpacaSourceConfig, cfg: CryptoConfig):
        self.t, self.alpaca, self.cfg = transport, alpaca, cfg
        self.base = f"/v1beta3/crypto/{cfg.location}"

    def _paged(self, path: str, key: str, params: dict) -> dict[str, list]:
        out: dict[str, list] = {}
        token = None
        while True:
            page = self.t.get(self.alpaca.data_base_url, path, {**params, "page_token": token})
            for sym, rows in (page.get(key) or {}).items():
                out.setdefault(sym, []).extend(rows)
            token = page.get("next_page_token")
            if not token:
                return out

    def daily_bars(self, symbols: Iterable[str], start: date, end: Optional[date] = None) -> dict[str, list[dict]]:
        start = max(start, self.cfg.history_start)
        params = {"symbols": ",".join(sorted(set(symbols))), "timeframe": "1Day", "start": start.isoformat(),
                  "end": end.isoformat() if end else None, "limit": 10000}
        return self._paged(f"{self.base}/bars", "bars", params)

    def latest_quotes(self, symbols: Iterable[str]) -> dict:
        return self.t.get(self.alpaca.data_base_url, f"{self.base}/latest/quotes", {"symbols": ",".join(sorted(set(symbols)))}).get("quotes") or {}

    def latest_orderbooks(self, symbols: Iterable[str]) -> dict:
        return self.t.get(self.alpaca.data_base_url, f"{self.base}/latest/orderbooks", {"symbols": ",".join(sorted(set(symbols)))}).get("orderbooks") or {}

    def trades(self, symbol: str, start: datetime, limit: int = 1000) -> list[dict]:
        page = self.t.get(self.alpaca.data_base_url, f"{self.base}/trades", {"symbols": symbol, "start": iso_utc(ensure_utc(start)), "limit": limit})
        return (page.get("trades") or {}).get(symbol, [])


def to_bars(symbol: str, rows: list[dict], now: datetime, venue: str = "alpaca_us") -> list[Bar]:
    """A daily bar covers 00:00 to 24:00 UTC. It is complete, and usable, only after it closes."""
    out = []
    for r in rows:
        start = parse_rfc3339(r["t"])
        end = start + timedelta(days=1)
        out.append(Bar("crypto", venue, symbol, "1Day", start, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]),
                       float(r["v"]) if r.get("v") is not None else None, end <= ensure_utc(now), VENDOR, LICENSE, end,
                       int(r["n"]) if r.get("n") is not None else None, float(r["vw"]) if r.get("vw") is not None else None))
    return out
