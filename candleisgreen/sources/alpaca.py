"""Alpaca client for daily US equity data and the asset list. Free plan, paper host only.

Response shapes follow Alpaca's published API documentation. They have not yet been
checked against a live response, because no paper keys exist in the build environment.
`AlpacaData` works with any transport: `HttpTransport` for the real API (keys from the
environment only) or `FakeAlpacaTransport` for offline tests and demos.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional, Protocol

from ..broker.base import assert_paper_endpoint
from ..core.config import AlpacaSourceConfig
from ..core.timeutil import ensure_utc, iso_utc, local_to_utc

MARKET_TZ = "America/New_York"
ASSETS_PATH = "/v2/assets"
BARS_PATH = "/v2/stocks/bars"
ACTIONS_PATH = "/v1/corporate-actions"
ACTION_TYPES = ("forward_split", "reverse_split", "cash_dividend", "stock_dividend", "name_change", "worthless_removal")


class MissingCredentialsError(RuntimeError):
    pass


class TooEarlyError(RuntimeError):
    """The free plan only serves consolidated history that ended at least the SIP delay ago."""


class Transport(Protocol):
    def get(self, base_url: str, path: str, params: dict[str, Any]) -> Any: ...


class HttpTransport:
    """Real HTTP calls. Keys come from APCA_API_KEY_ID and APCA_API_SECRET_KEY only."""

    def __init__(self, cfg: AlpacaSourceConfig):
        self.cfg = cfg
        assert_paper_endpoint(cfg.trading_base_url + "/")
        self.key_id = os.environ.get("APCA_API_KEY_ID")
        self.secret = os.environ.get("APCA_API_SECRET_KEY")
        if not self.key_id or not self.secret:
            raise MissingCredentialsError("set APCA_API_KEY_ID and APCA_API_SECRET_KEY (paper keys) in the environment")

    def get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{base_url}{path}?{query}" if query else f"{base_url}{path}"
        headers = {"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret, "Accept": "application/json"}
        delay = 1.0
        for attempt in range(self.cfg.max_retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.cfg.request_timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.cfg.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except urllib.error.URLError:
                if attempt < self.cfg.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")


def session_close_utc(day: date, close_hhmm: str) -> datetime:
    return local_to_utc(day, close_hhmm, MARKET_TZ)


class AlpacaData:
    def __init__(self, transport: Transport, cfg: AlpacaSourceConfig, close_hhmm: str = "16:00"):
        self.t = transport
        self.cfg = cfg
        self.close_hhmm = close_hhmm

    def assets(self, status: str) -> list[dict]:
        if status not in ("active", "inactive"):
            raise ValueError("status must be active or inactive")
        return list(self.t.get(self.cfg.trading_base_url, ASSETS_PATH, {"status": status, "asset_class": "us_equity"}))

    def latest_allowed_end(self, now: datetime) -> datetime:
        return ensure_utc(now) - timedelta(minutes=self.cfg.sip_delay_minutes)

    def daily_bars(self, symbols: Iterable[str], start: date, end: date, now: datetime) -> dict[str, list[dict]]:
        """Daily bars, unadjusted, for every symbol between two session dates inclusive."""
        end_ts = session_close_utc(end, self.close_hhmm)
        if self.cfg.bars_feed == "sip" and end_ts > self.latest_allowed_end(now):
            raise TooEarlyError(f"bars for {end} are not free until {self.cfg.sip_delay_minutes} minutes after the close")
        symbols = sorted(set(symbols))
        out: dict[str, list[dict]] = {}
        step = self.cfg.symbols_per_request
        for i in range(0, len(symbols), step):
            batch = symbols[i:i + step]
            token: Optional[str] = None
            while True:
                params = {
                    "symbols": ",".join(batch), "timeframe": "1Day", "start": start.isoformat(),
                    "end": iso_utc(end_ts), "feed": self.cfg.bars_feed, "adjustment": self.cfg.adjustment,
                    "limit": 10000, "page_token": token,
                }
                page = self.t.get(self.cfg.data_base_url, BARS_PATH, params)
                for symbol, bars in (page.get("bars") or {}).items():
                    out.setdefault(symbol, []).extend(bars)
                token = page.get("next_page_token")
                if not token:
                    break
        return out

    def corporate_actions(self, symbols: Iterable[str], start: date, end: date) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        token: Optional[str] = None
        while True:
            params = {
                "symbols": ",".join(sorted(set(symbols))), "types": ",".join(ACTION_TYPES),
                "start": start.isoformat(), "end": end.isoformat(), "limit": 1000, "page_token": token,
            }
            page = self.t.get(self.cfg.data_base_url, ACTIONS_PATH, params)
            for kind, rows in (page.get("corporate_actions") or {}).items():
                out.setdefault(kind, []).extend(rows)
            token = page.get("next_page_token")
            if not token:
                break
        return out
