"""Predict first (spec Teaching). The user states target, horizon and probability before the
reveal. Each prediction is scored with the Brier score against a 50% baseline once its
outcome is known, and a calibration table compares stated probabilities with outcomes."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.sqlite_shared import connect as sqlite_connect
from ..core.ids import make_id
from ..core.timeutil import ensure_utc, from_micros, to_micros
from ..data.instruments import InstrumentMaster
from ..data.pit_store import PointInTimeStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY, user TEXT NOT NULL, symbol TEXT NOT NULL, instrument_id TEXT NOT NULL,
    direction TEXT NOT NULL, horizon_days INTEGER NOT NULL, probability REAL NOT NULL,
    made_at INTEGER NOT NULL, made_at_wall INTEGER NOT NULL, context TEXT NOT NULL,
    outcome INTEGER, resolved_at INTEGER
);
"""


class PredictionError(ValueError):
    pass


@dataclass(frozen=True)
class Calibration:
    bins: list[dict]
    brier: Optional[float]
    baseline_brier: float
    resolved: int


class Predictions:
    def __init__(self, path: str | Path, shared_across_threads: bool = False):
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)

    def add(self, user: str, symbol: str, master: InstrumentMaster, direction: str, horizon_days: int,
            probability: float, made_at: datetime, wall: datetime, context: str = "live") -> str:
        if direction not in ("up", "down"):
            raise PredictionError("direction must be up or down")
        if not 0.0 <= probability <= 1.0:
            raise PredictionError("probability must be between 0 and 1")
        iid = master.instrument_for_symbol(symbol)
        if iid is None:
            raise PredictionError(f"unknown ticker {symbol}")
        pid = make_id("pred", {"user": user, "iid": iid, "dir": direction, "h": horizon_days, "p": probability,
                               "at": ensure_utc(made_at), "ctx": context})
        self.conn.execute("INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            pid, user, symbol, iid, direction, horizon_days, probability, to_micros(ensure_utc(made_at)),
            to_micros(ensure_utc(wall)), context, None, None))
        return pid

    def resolve(self, store: PointInTimeStore, now: datetime) -> int:
        """Resolve every prediction whose horizon has passed, using only data usable by `now`."""
        done = 0
        for pid, iid, direction, h, made in self.conn.execute(
                "SELECT prediction_id, instrument_id, direction, horizon_days, made_at FROM predictions "
                "WHERE outcome IS NULL").fetchall():
            start_t = from_micros(made)
            end_t = start_t + timedelta(days=h)
            if ensure_utc(now) < end_t:
                continue
            before = store.as_of(start_t).series(iid, "close")
            after = store.as_of(min(ensure_utc(now), end_t + timedelta(days=5))).series(iid, "close")
            after = [o for o in after if o.event_time >= end_t - timedelta(days=1)]
            if not before or not after:
                continue
            went_up = after[0].value > before[-1].value
            outcome = int(went_up == (direction == "up"))
            self.conn.execute("UPDATE predictions SET outcome = ?, resolved_at = ? WHERE prediction_id = ?",
                              (outcome, to_micros(ensure_utc(now)), pid))
            done += 1
        return done

    def list(self, user: str) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM predictions WHERE user = ? ORDER BY made_at DESC", (user,))
        cols = [c[0] for c in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["made_at"] = from_micros(d["made_at"]).isoformat()
            d["made_at_wall"] = from_micros(d["made_at_wall"]).isoformat()
            d["resolved_at"] = from_micros(d["resolved_at"]).isoformat() if d["resolved_at"] else None
            out.append(d)
        return out

    def calibration(self, user: str, edges=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0001),
                    replay_clock: Optional[datetime] = None) -> Calibration:
        """Resolved predictions only. With a replay clock, a replay prediction counts only once the
        clock has passed its horizon, so the table never reveals an outcome early."""
        raw = self.conn.execute(
            "SELECT probability, outcome, context, made_at, horizon_days FROM predictions WHERE user = ? AND outcome IS NOT NULL",
            (user,)).fetchall()
        rows = []
        for p, o, ctx, made, h in raw:
            due = from_micros(made) + timedelta(days=h)
            if ctx == "replay" and replay_clock is not None and due > ensure_utc(replay_clock):
                continue
            rows.append((p, o))
        bins = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = [(p, o) for p, o in rows if lo <= p < hi]
            bins.append({"range": f"{lo:.1f} to {min(hi, 1.0):.1f}", "count": len(sel),
                         "mean_stated": sum(p for p, _ in sel) / len(sel) if sel else None,
                         "hit_rate": sum(o for _, o in sel) / len(sel) if sel else None})
        brier = sum((p - o) ** 2 for p, o in rows) / len(rows) if rows else None
        return Calibration(bins, brier, 0.25, len(rows))
