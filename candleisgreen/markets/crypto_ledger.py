"""Crypto practice account that survives restarts. Simulation only, no broker.

Storage is an append-only ledger in SQLite. Each order, filled or blocked, is one INSERT that
holds the order, its checks, its fill and the account state after it, so a crash can never
leave a fill without its cash change. Each row names the row before it, and that name is
unique, so two writers starting from the same state cannot both succeed: the second is
refused and retried from the new state.

Every order carries a client order ID. Sending the same ID again returns the first result and
changes nothing. Reusing an ID for a different order is refused.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.config import CryptoConfig
from ..core.sqlite_shared import connect
from ..core.timeutil import ensure_utc, from_micros, to_micros
from .crypto import CryptoSimulator

_DDL = """
CREATE TABLE IF NOT EXISTS crypto_practice (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  client_order_id TEXT NOT NULL UNIQUE,
  prev_order_id TEXT UNIQUE,
  created_us INTEGER NOT NULL,
  side TEXT NOT NULL, symbol TEXT NOT NULL, notional REAL NOT NULL,
  status TEXT NOT NULL, checks TEXT NOT NULL, fill TEXT,
  cash_after REAL NOT NULL, holdings_after TEXT NOT NULL
);
"""
GENESIS = "start"


class OrderIdReusedError(ValueError):
    pass


class ConcurrentWriteError(RuntimeError):
    pass


class CryptoPractice:
    def __init__(self, path: str | Path, cfg: CryptoConfig, starting_cash: float):
        self.cfg, self.starting_cash = cfg, starting_cash
        self.conn = connect(path, shared_across_threads=True)
        self.conn.executescript(_DDL)
        self._lock = threading.RLock()

    def _last(self):
        return self.conn.execute("SELECT client_order_id, cash_after, holdings_after FROM crypto_practice ORDER BY seq DESC LIMIT 1").fetchone()

    def state(self) -> tuple[float, dict[str, float]]:
        row = self._last()
        return (self.starting_cash, {}) if row is None else (row[1], json.loads(row[2]))

    def volume_30d(self, now: datetime) -> float:
        since = to_micros(ensure_utc(now) - timedelta(days=30))
        row = self.conn.execute("SELECT COALESCE(SUM(notional), 0) FROM crypto_practice WHERE status='filled' AND created_us >= ?", (since,)).fetchone()
        return float(row[0])

    def fills(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute("SELECT client_order_id, created_us, fill FROM crypto_practice WHERE status='filled' ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{"client_order_id": r[0], "time": from_micros(r[1]).isoformat(), **json.loads(r[2])} for r in rows]

    def _existing(self, cid: str):
        return self.conn.execute("SELECT side, symbol, notional, status, checks, fill, cash_after, holdings_after FROM crypto_practice WHERE client_order_id=?", (cid,)).fetchone()

    def order(self, client_order_id: str, side: str, symbol: str, notional: float, book: dict, now: datetime,
              mids: dict[str, float]) -> dict:
        if not client_order_id or len(client_order_id) > 64:
            raise ValueError("a client order ID of 1 to 64 characters is required")
        with self._lock:
            prior = self._existing(client_order_id)
            if prior is not None:
                if (prior[0], prior[1], round(prior[2], 8)) != (side, symbol, round(notional, 8)):
                    raise OrderIdReusedError(f"client order ID {client_order_id} was already used for a different order")
                return {"status": prior[3], "checks": json.loads(prior[4]), "fill": json.loads(prior[5]) if prior[5] else None,
                        "cash": prior[6], "holdings": json.loads(prior[7]), "duplicate": True}
            for _ in range(3):
                last = self._last()
                cash, holdings = self.state()
                sim = CryptoSimulator(self.cfg, cash=cash, holdings=dict(holdings), volume_30d_usd=self.volume_30d(now))
                equity = sim.value(mids)
                if equity is None:
                    equity = cash
                status, checks, fill = sim.order(side, symbol, notional, book, now, equity, mids)
                fill_json = None if fill is None else json.dumps({k: v for k, v in asdict(fill).items() if k != "time"})
                try:
                    self.conn.execute(
                        "INSERT INTO crypto_practice (client_order_id, prev_order_id, created_us, side, symbol, notional, status, checks, fill, cash_after, holdings_after) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (client_order_id, last[0] if last else GENESIS, to_micros(ensure_utc(now)), side, symbol, notional, status,
                         json.dumps([asdict(c) for c in checks]), fill_json, sim.cash, json.dumps(sim.holdings)))
                except sqlite3.IntegrityError:
                    if self._existing(client_order_id) is not None:
                        return self.order(client_order_id, side, symbol, notional, book, now, mids)
                    continue  # another writer moved the account. Start again from its new state
                return {"status": status, "checks": [asdict(c) for c in checks], "fill": json.loads(fill_json) if fill_json else None,
                        "cash": sim.cash, "holdings": sim.holdings, "duplicate": False}
            raise ConcurrentWriteError("the practice account kept changing during the order. Try again")
