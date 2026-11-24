"""Practitioner claim scoring (spec C.9 and Source registry). Only forecasts and testable claims
are scored. A domain becomes a signal only after enough scored claims and a hit rate whose
interval lies above the 50% baseline. Fame, followers and reputation carry no weight."""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from scipy.stats import norm

from ..core.config import CriteriaConfig
from ..core.ids import make_id
from ..core.timeutil import ensure_utc, from_micros, to_micros
from ..data.pit_store import PointInTimeStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS practitioner_claims (
    claim_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, domain TEXT NOT NULL, instrument_id TEXT NOT NULL,
    direction TEXT NOT NULL, horizon_days INTEGER NOT NULL, probability REAL, made_at INTEGER NOT NULL, outcome INTEGER
);
"""


def wilson(hits: int, n: int, level: float) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    z = norm.ppf(1 - (1 - level) / 2)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


class PractitionerBook:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.executescript(_SCHEMA)

    def add(self, source_id: str, domain: str, instrument_id: str, direction: str, horizon_days: int,
            made_at: datetime, probability: Optional[float] = None) -> str:
        if direction not in ("up", "down"):
            raise ValueError("a scored claim needs a direction")
        cid = make_id("pclaim", {"s": source_id, "d": domain, "i": instrument_id, "dir": direction, "h": horizon_days,
                                 "at": ensure_utc(made_at)})
        self.conn.execute("INSERT OR IGNORE INTO practitioner_claims VALUES (?,?,?,?,?,?,?,?,?)",
                          (cid, source_id, domain, instrument_id, direction, horizon_days, probability,
                           to_micros(ensure_utc(made_at)), None))
        return cid

    def resolve(self, store: PointInTimeStore, now: datetime) -> int:
        done = 0
        for cid, iid, direction, h, made in self.conn.execute(
                "SELECT claim_id, instrument_id, direction, horizon_days, made_at FROM practitioner_claims WHERE outcome IS NULL").fetchall():
            start = from_micros(made)
            end = start + timedelta(days=h)
            if ensure_utc(now) < end:
                continue
            before = store.as_of(start).series(iid, "close")
            after = [o for o in store.as_of(ensure_utc(now)).series(iid, "close") if o.event_time >= end - timedelta(days=1)]
            if not before or not after:
                continue
            up = after[0].value > before[-1].value
            self.conn.execute("UPDATE practitioner_claims SET outcome = ? WHERE claim_id = ?",
                              (int(up == (direction == "up")), cid))
            done += 1
        return done

    def score(self, source_id: str, domain: str, cfg: CriteriaConfig) -> dict:
        rows = self.conn.execute("SELECT outcome, probability FROM practitioner_claims WHERE source_id = ? AND domain = ? "
                                 "AND outcome IS NOT NULL", (source_id, domain)).fetchall()
        n = len(rows)
        hits = sum(r[0] for r in rows)
        lo, hi = wilson(hits, n, cfg.practitioner_interval_level)
        probs = [(r[1], r[0]) for r in rows if r[1] is not None]
        brier = sum((p - o) ** 2 for p, o in probs) / len(probs) if probs else None
        enough = n >= cfg.practitioner_min_claims
        return {"source_id": source_id, "domain": domain, "scored_claims": n, "hit_rate": hits / n if n else None,
                "interval": [lo, hi], "baseline": 0.5, "brier": brier,
                "track_record": "INSUFFICIENT DATA" if not enough else ("BEATS BASELINE" if lo > 0.5 else "DOES NOT BEAT BASELINE"),
                "eligible_as_signal": bool(enough and lo > 0.5)}
