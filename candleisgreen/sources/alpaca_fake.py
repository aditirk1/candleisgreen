"""Offline stand-in for the Alpaca API. Synthetic data only, labeled as such everywhere.

It serves a deterministic market built to exercise the pipeline: steady uptrend and
downtrend names, a flat name, a 2-for-1 split, a cash dividend, a ticker change that keeps
its asset ID, a delisting, and an ETF. It paginates bars so token handling is tested.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..core.timeutil import ensure_utc, local_to_utc
from .alpaca import ACTIONS_PATH, ASSETS_PATH, BARS_PATH, MARKET_TZ


@dataclass(frozen=True)
class FakeAsset:
    asset_id: str
    symbol: str
    name: str
    exchange: str
    drift: float  # daily log drift
    start_price: float
    delisted_on: Optional[date] = None
    renamed_on: Optional[date] = None
    new_symbol: Optional[str] = None
    split_on: Optional[date] = None
    dividend_on: Optional[date] = None


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@dataclass
class FakeMarket:
    start: date = date(2025, 6, 2)
    end: date = date(2026, 11, 20)
    assets: tuple = field(default_factory=lambda: (
        FakeAsset("a-0001", "UPCO", "Upward Industries Inc", "NYSE", 0.0012, 40.0),
        FakeAsset("a-0002", "DNCO", "Downward Holdings Corp", "NASDAQ", -0.0010, 60.0),
        FakeAsset("a-0003", "FLAT", "Level Utilities Co", "NYSE", 0.0, 30.0, dividend_on=date(2026, 3, 16)),
        FakeAsset("a-0004", "SPLT", "Splitwell Technologies Inc", "NASDAQ", 0.0009, 180.0, split_on=date(2026, 5, 4)),
        FakeAsset("a-0005", "RNME", "Renamed Biosciences Inc", "NASDAQ", 0.0006, 25.0,
                  renamed_on=date(2026, 8, 3), new_symbol="RNMX"),
        FakeAsset("a-0006", "DLST", "Departed Retail Inc", "NYSE", -0.0015, 20.0, delisted_on=date(2026, 9, 30)),
        FakeAsset("a-0007", "BIGX", "Broad Index ETF Trust", "ARCA", 0.0004, 400.0),
    ))
    page_size: int = 250
    daily_noise: float = 0.004
    days: list = field(init=False)

    def __post_init__(self):
        self.days = weekdays(self.start, self.end)

    def _noise(self, a: FakeAsset):
        """Seeded random walk, 0.4% daily volatility, so synthetic prices are not unrealistically smooth."""
        cache = self.__dict__.setdefault("_noise_cache", {})
        if a.asset_id not in cache:
            import numpy as np

            rng = np.random.default_rng(int(a.asset_id.split("-")[1]))
            cache[a.asset_id] = np.cumsum(rng.normal(0.0, self.daily_noise, len(self.days)))
        return cache[a.asset_id]

    def symbol_on(self, a: FakeAsset, day: date) -> str:
        return a.new_symbol if a.renamed_on and day >= a.renamed_on else a.symbol

    def close(self, a: FakeAsset, i: int, day: date) -> float:
        wiggle = 0.01 * math.sin(i / 7.0 + len(a.symbol))
        price = a.start_price * math.exp(a.drift * i + wiggle + self._noise(a)[i])
        if a.split_on and day >= a.split_on:
            price /= 2.0
        return round(price, 2)

    def bars_for(self, a: FakeAsset) -> list[tuple[date, dict]]:
        out = []
        for i, day in enumerate(self.days):
            if a.delisted_on and day > a.delisted_on:
                break
            c = self.close(a, i, day)
            vol = 2_000_000 + 10_000 * (i % 13)
            t = local_to_utc(day, "00:00", MARKET_TZ)
            out.append((day, {"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": round(c * 0.997, 2), "h": round(c * 1.01, 2),
                              "l": round(c * 0.99, 2), "c": c, "v": vol, "n": 15000, "vw": round(c * 1.001, 2)}))
        return out

    # API surface ---------------------------------------------------------------------------

    def get(self, base_url: str, path: str, params: dict[str, Any], now: Optional[datetime] = None) -> Any:
        if path == ASSETS_PATH:
            return self._assets(params["status"], now)
        if path == BARS_PATH:
            return self._bars(params)
        if path == ACTIONS_PATH:
            return self._actions(params)
        if path == "/v2/stocks/quotes/latest":
            return self._quotes(params, now)
        if path == "/v2/clock":
            return self._clock(now)
        raise KeyError(f"fake Alpaca has no route {path}")

    def _quotes(self, params: dict[str, Any], now: Optional[datetime]) -> dict:
        """Synthetic quote around the latest close on or before today, stamped now."""
        when = ensure_utc(now) if now else local_to_utc(self.end, "16:00", MARKET_TZ)
        out = {}
        for sym in params["symbols"].split(","):
            a = next((x for x in self.assets if self.symbol_on(x, when.date()) == sym), None)
            if a is None or (a.delisted_on and when.date() > a.delisted_on):
                continue
            bars = [b for d, b in self.bars_for(a) if d <= when.date()]
            if not bars:
                continue
            c = bars[-1]["c"]
            out[sym] = {"ap": round(c * 1.0004, 4), "as": 100, "ax": "V", "bp": round(c * 0.9996, 4), "bs": 100, "bx": "V",
                        "c": ["R"], "t": when.strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z", "z": "C"}
        return {"quotes": out}

    def _clock(self, now: Optional[datetime]) -> dict:
        from zoneinfo import ZoneInfo

        from ..calendars import is_trading_day

        local = ensure_utc(now).astimezone(ZoneInfo(MARKET_TZ)) if now else None
        is_open = bool(local and is_trading_day(local.date()) and
                       (local.hour, local.minute) >= (9, 30) and (local.hour, local.minute) < (16, 0))
        return {"is_open": is_open, "timestamp": local.isoformat() if local else None,
                "next_open": None, "next_close": None}

    def _assets(self, status: str, now: Optional[datetime]) -> list[dict]:
        today = (ensure_utc(now).date() if now else self.end)
        rows = []
        for a in self.assets:
            inactive = bool(a.delisted_on and today > a.delisted_on)
            if (status == "inactive") != inactive:
                continue
            rows.append({"id": a.asset_id, "class": "us_equity", "exchange": a.exchange,
                         "symbol": self.symbol_on(a, today), "name": a.name,
                         "status": "inactive" if inactive else "active", "tradable": not inactive,
                         "marginable": True, "shortable": True, "fractionable": True, "attributes": []})
        return rows

    def _bars(self, params: dict[str, Any]) -> dict:
        wanted = set(params["symbols"].split(","))
        start = date.fromisoformat(params["start"])
        end = ensure_utc(datetime.fromisoformat(params["end"].replace("Z", "+00:00"))).date()
        flat: list[tuple[str, dict]] = []
        for a in self.assets:
            # Alpaca maps history to the current symbol. Old symbols are served too.
            names = {a.symbol} | ({a.new_symbol} if a.new_symbol else set())
            hit = names & wanted
            if not hit:
                continue
            for day, bar in self.bars_for(a):
                if start <= day <= end:
                    flat.append((sorted(hit)[0], bar))
        offset = int(params.get("page_token") or 0)
        page = flat[offset: offset + self.page_size]
        out: dict[str, list[dict]] = {}
        for symbol, bar in page:
            out.setdefault(symbol, []).append(bar)
        nxt = offset + self.page_size
        return {"bars": out, "next_page_token": str(nxt) if nxt < len(flat) else None}

    def _actions(self, params: dict[str, Any]) -> dict:
        start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
        out: dict[str, list[dict]] = {}
        for a in self.assets:
            if a.split_on and start <= a.split_on <= end:
                out.setdefault("forward_splits", []).append(
                    {"id": f"fs-{a.asset_id}", "symbol": a.symbol, "new_rate": 2, "old_rate": 1,
                     "ex_date": a.split_on.isoformat(), "process_date": a.split_on.isoformat()})
            if a.dividend_on and start <= a.dividend_on <= end:
                out.setdefault("cash_dividends", []).append(
                    {"id": f"cd-{a.asset_id}", "symbol": a.symbol, "rate": 0.25,
                     "ex_date": a.dividend_on.isoformat(), "process_date": a.dividend_on.isoformat()})
            if a.renamed_on and start <= a.renamed_on <= end:
                out.setdefault("name_changes", []).append(
                    {"id": f"nc-{a.asset_id}", "old_symbol": a.symbol, "new_symbol": a.new_symbol,
                     "process_date": a.renamed_on.isoformat()})
            if a.delisted_on and start <= a.delisted_on <= end:
                out.setdefault("worthless_removals", []).append(
                    {"id": f"wr-{a.asset_id}", "symbol": a.symbol, "process_date": a.delisted_on.isoformat()})
        return {"corporate_actions": out, "next_page_token": None}


class FakeAlpacaTransport:
    """Transport wrapper. `now` controls which assets look active, like a real snapshot."""

    synthetic = True

    def __init__(self, market: Optional[FakeMarket] = None, now: Optional[datetime] = None):
        self.market = market or FakeMarket()
        self.now = now
        self.calls: list[tuple[str, dict]] = []

    def get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        self.calls.append((path, dict(params)))
        return self.market.get(base_url, path, params, self.now)
