"""Point-in-time store for asset classes beyond US stocks (crypto, forex, futures positioning).

Separate from the stock store so nothing in the stock pipeline changes. Same rules:
1. Append only. A revised bar or report is a new row with a higher vintage.
2. Reads take a decision time and return only rows whose first_usable_at is before it,
   latest vintage per key.
3. Every row carries its vendor and license.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from ..core.sqlite_shared import connect
from ..core.timeutil import ensure_utc, from_micros, to_micros

_DDL = """
CREATE TABLE IF NOT EXISTS bars (
  asset_class TEXT NOT NULL, venue TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  start_us INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL, trades INTEGER, vwap REAL,
  bid_close REAL, ask_close REAL, complete INTEGER NOT NULL,
  vendor TEXT NOT NULL, license TEXT NOT NULL, ingested_us INTEGER NOT NULL, first_usable_us INTEGER NOT NULL,
  vintage INTEGER NOT NULL,
  PRIMARY KEY (venue, symbol, timeframe, start_us, vintage)
);
CREATE TABLE IF NOT EXISTS reports (
  dataset TEXT NOT NULL, market_code TEXT NOT NULL, report_date TEXT NOT NULL, body TEXT NOT NULL,
  vendor TEXT NOT NULL, license TEXT NOT NULL, ingested_us INTEGER NOT NULL, first_usable_us INTEGER NOT NULL,
  vintage INTEGER NOT NULL,
  PRIMARY KEY (dataset, market_code, report_date, vintage)
);
"""

_BAR_COLS = ("open", "high", "low", "close", "volume", "trades", "vwap", "bid_close", "ask_close")


@dataclass(frozen=True)
class Bar:
    asset_class: str
    venue: str
    symbol: str
    timeframe: str
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    complete: bool
    vendor: str
    license: str
    first_usable_at: datetime
    trades: Optional[int] = None
    vwap: Optional[float] = None
    bid_close: Optional[float] = None
    ask_close: Optional[float] = None


class MarketStore:
    def __init__(self, path: str | Path, shared: bool = True):
        self.conn = connect(path, shared_across_threads=shared)
        self.conn.executescript(_DDL)

    def add_bars(self, bars: Iterable[Bar], ingested_at: datetime) -> int:
        """Store bars. An incomplete bar is never stored, and an unchanged bar is not stored twice."""
        n = 0
        for b in bars:
            if not b.complete:
                continue
            key = (b.venue, b.symbol, b.timeframe, to_micros(ensure_utc(b.start)))
            last = self.conn.execute(
                f"SELECT vintage, {', '.join(_BAR_COLS)} FROM bars WHERE venue=? AND symbol=? AND timeframe=? AND start_us=? "
                "ORDER BY vintage DESC LIMIT 1", key).fetchone()
            vals = tuple(getattr(b, c) for c in _BAR_COLS)
            if last and tuple(last[1:]) == vals:
                continue
            vintage = (last[0] + 1) if last else 1
            first_usable = max(to_micros(ensure_utc(b.first_usable_at)), to_micros(ensure_utc(ingested_at))) if last else to_micros(ensure_utc(b.first_usable_at))
            self.conn.execute(
                "INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (b.asset_class, b.venue, b.symbol, b.timeframe, key[3], b.open, b.high, b.low, b.close, b.volume, b.trades, b.vwap,
                 b.bid_close, b.ask_close, 1, b.vendor, b.license, to_micros(ensure_utc(ingested_at)), first_usable, vintage))
            n += 1
        return n

    def bars(self, venue: str, symbol: str, timeframe: str, as_of: datetime, start: Optional[datetime] = None) -> list[Bar]:
        cutoff = to_micros(ensure_utc(as_of))
        lo = to_micros(ensure_utc(start)) if start else 0
        rows = self.conn.execute(
            "SELECT * FROM bars b WHERE venue=? AND symbol=? AND timeframe=? AND first_usable_us < ? AND start_us >= ? "
            "AND vintage = (SELECT MAX(vintage) FROM bars c WHERE c.venue=b.venue AND c.symbol=b.symbol AND c.timeframe=b.timeframe "
            "AND c.start_us=b.start_us AND c.first_usable_us < ?) ORDER BY start_us", (venue, symbol, timeframe, cutoff, lo, cutoff)).fetchall()
        return [Bar(r[0], r[1], r[2], r[3], from_micros(r[4]), r[5], r[6], r[7], r[8], r[9], bool(r[14]), r[15], r[16],
                    from_micros(r[18]), r[10], r[11], r[12], r[13]) for r in rows]

    def symbols(self, asset_class: str) -> list[tuple[str, str, int, Optional[datetime]]]:
        """(venue, symbol, number of bars, last bar start) for each stored series."""
        rows = self.conn.execute("SELECT venue, symbol, COUNT(DISTINCT start_us), MAX(start_us) FROM bars WHERE asset_class=? "
                                 "GROUP BY venue, symbol ORDER BY symbol", (asset_class,)).fetchall()
        return [(r[0], r[1], r[2], from_micros(r[3]) if r[3] else None) for r in rows]

    def add_report(self, dataset: str, market_code: str, report_date: date, body: dict, vendor: str, license: str,
                   ingested_at: datetime, first_usable_at: datetime) -> bool:
        text = json.dumps(body, sort_keys=True)
        last = self.conn.execute("SELECT vintage, body FROM reports WHERE dataset=? AND market_code=? AND report_date=? "
                                 "ORDER BY vintage DESC LIMIT 1", (dataset, market_code, report_date.isoformat())).fetchone()
        if last and last[1] == text:
            return False
        vintage = (last[0] + 1) if last else 1
        usable = first_usable_at if not last else max(ensure_utc(first_usable_at), ensure_utc(ingested_at))
        self.conn.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?)",
                          (dataset, market_code, report_date.isoformat(), text, vendor, license, to_micros(ensure_utc(ingested_at)),
                           to_micros(ensure_utc(usable)), vintage))
        return True

    def reports(self, dataset: str, market_code: str, as_of: datetime) -> list[tuple[date, dict, datetime]]:
        cutoff = to_micros(ensure_utc(as_of))
        rows = self.conn.execute(
            "SELECT report_date, body, first_usable_us FROM reports r WHERE dataset=? AND market_code=? AND first_usable_us < ? "
            "AND vintage = (SELECT MAX(vintage) FROM reports s WHERE s.dataset=r.dataset AND s.market_code=r.market_code "
            "AND s.report_date=r.report_date AND s.first_usable_us < ?) ORDER BY report_date", (dataset, market_code, cutoff, cutoff)).fetchall()
        return [(date.fromisoformat(r[0]), json.loads(r[1]), from_micros(r[2])) for r in rows]
