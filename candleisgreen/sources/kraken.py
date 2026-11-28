"""Kraken public market data, read only. Optional comparison source for crypto.

The public endpoints need no key (checked live 2026-11-28: OHLC and Ticker answered). Kraken's
Global Terms, read on 2026-11-28 only in part, appear to restrict third-party applications
and automated data extraction without written consent. So the license `kraken_public` is
unverified, and this client refuses to fetch until Aditi has read the terms and marked it
permitted in config/licenses.yaml.

OHLC returns at most the 720 most recent intervals. Older data cannot be fetched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..core.licenses import LicenseRegistry, load_licenses
from ..markets.store import Bar

BASE = "https://api.kraken.com"
LICENSE = "kraken_public"
VENDOR = "kraken"


class KrakenError(RuntimeError):
    pass


def _result(page: dict) -> dict:
    if page.get("error"):
        raise KrakenError("; ".join(page["error"]))
    return page.get("result") or {}


def parse_ohlc(page: dict, symbol: str, now: datetime) -> list[Bar]:
    """Rows are [time, open, high, low, close, vwap, volume, count]. The last row is the open interval."""
    res = _result(page)
    key = next(k for k in res if k != "last")
    out = []
    rows = res[key]
    for i, row in enumerate(rows):
        start = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
        end = start + timedelta(days=1)
        # Kraken documents the last entry as the current, uncommitted interval.
        complete = end <= now and i < len(rows) - 1
        out.append(Bar("crypto", "kraken", symbol, "1Day", start, float(row[1]), float(row[2]), float(row[3]), float(row[4]),
                       float(row[6]), complete, VENDOR, LICENSE, end, int(row[7]), float(row[5])))
    return out


def parse_ticker(page: dict) -> dict:
    """Best bid and ask and last trade per pair, from Kraken's a, b and c arrays."""
    out = {}
    for pair, t in _result(page).items():
        out[pair] = {"ask": float(t["a"][0]), "bid": float(t["b"][0]), "last": float(t["c"][0])}
    return out


class KrakenPublic:
    def __init__(self, transport, licenses: LicenseRegistry | None = None):
        (licenses or load_licenses()).assert_use([LICENSE], "research")
        self.t = transport

    def daily(self, pair: str, symbol: str, now: datetime) -> list[Bar]:
        return parse_ohlc(self.t.get(BASE, "/0/public/OHLC", {"pair": pair, "interval": 1440}), symbol, now)

    def ticker(self, pairs: list[str]) -> dict:
        return parse_ticker(self.t.get(BASE, "/0/public/Ticker", {"pair": ",".join(pairs)}))
