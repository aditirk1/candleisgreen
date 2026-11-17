"""Point-in-time store on DuckDB, exportable to Parquet.

Rules:
1. Rows are append-only. A revised value is a new row with a higher vintage.
2. Models read through `as_of(decision_time)`, which returns only rows whose
   `first_usable_at` is strictly before the decision time, latest usable vintage per key.
3. `assert_no_lookahead` is the build-failing guard. Any consumer that received
   observations by another route must pass them through it before producing output.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import duckdb

from ..core.ids import make_id
from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc, from_micros, to_micros


class LookaheadError(RuntimeError):
    """An input was not usable at the decision time. This must fail the build."""


_TIME_COLS = ("event_time", "published_at", "vendor_available_at", "ingested_at", "first_usable_at")
_COLUMNS = (
    "observation_id", "instrument_id", "vendor", "raw_symbol", "exchange", "field", "value",
    *_TIME_COLS, "timezone", "currency", "adjustment_method", "vintage", "missing_flag",
    "license", "collection_mode",
)

_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    observation_id VARCHAR PRIMARY KEY,
    instrument_id VARCHAR NOT NULL, vendor VARCHAR NOT NULL, raw_symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL, field VARCHAR NOT NULL, value DOUBLE,
    event_time BIGINT NOT NULL, published_at BIGINT NOT NULL, vendor_available_at BIGINT NOT NULL,
    ingested_at BIGINT NOT NULL, first_usable_at BIGINT NOT NULL,
    timezone VARCHAR NOT NULL, currency VARCHAR NOT NULL, adjustment_method VARCHAR NOT NULL,
    vintage INTEGER NOT NULL, missing_flag BOOLEAN NOT NULL, license VARCHAR NOT NULL,
    collection_mode VARCHAR NOT NULL
)
"""


def assert_no_lookahead(observations: Iterable[Observation], decision_time: datetime) -> None:
    cutoff = ensure_utc(decision_time)
    late = [o for o in observations if o.first_usable_at >= cutoff]
    if late:
        worst = max(late, key=lambda o: o.first_usable_at)
        raise LookaheadError(
            f"{len(late)} input(s) not usable before {cutoff.isoformat()}. "
            f"Example {worst.observation_id} {worst.instrument_id} {worst.field} "
            f"first_usable_at {worst.first_usable_at.isoformat()}"
        )


def snapshot_id(observations: Sequence[Observation]) -> str:
    return make_id("snap", sorted(o.observation_id for o in observations))


def _to_row(obs: Observation) -> tuple:
    data = obs.model_dump()
    out = [obs.observation_id]
    for col in _COLUMNS[1:]:
        value = data[col]
        if col in _TIME_COLS:
            value = to_micros(value)
        elif col == "collection_mode":
            value = value.value
        out.append(value)
    return tuple(out)


def _from_row(row: tuple) -> Observation:
    data = dict(zip(_COLUMNS, row))
    data.pop("observation_id")
    for col in _TIME_COLS:
        data[col] = from_micros(data[col])
    data["collection_mode"] = CollectionMode(data["collection_mode"])
    return Observation(**data)


class AsOfView:
    """A read-only view of what was known strictly before one decision time."""

    def __init__(self, store: "PointInTimeStore", decision_time: datetime):
        self.decision_time = ensure_utc(decision_time)
        self._store = store

    def series(self, instrument_id: str, field: str) -> list[Observation]:
        """Latest usable vintage per event_time, ordered by event_time."""
        rows = self._store._conn.execute(
            f"""
            SELECT {", ".join(_COLUMNS)} FROM (
                SELECT *, row_number() OVER (PARTITION BY instrument_id, vendor, field, event_time
                                             ORDER BY vintage DESC) AS rn
                FROM observations
                WHERE instrument_id = ? AND field = ? AND first_usable_at < ?
            ) WHERE rn = 1 ORDER BY event_time
            """,
            [instrument_id, field, to_micros(self.decision_time)],
        ).fetchall()
        out = [_from_row(r) for r in rows]
        assert_no_lookahead(out, self.decision_time)
        return out


class PointInTimeStore:
    def __init__(self, path: str | Path = ":memory:"):
        self._conn = duckdb.connect(str(path))
        self._conn.execute(_DDL)

    def close(self) -> None:
        self._conn.close()

    def add(self, observations: Iterable[Observation]) -> int:
        """Append observations. Returns the count of new rows. Duplicates are ignored."""
        added = 0
        for obs in observations:
            row = _to_row(obs)
            exists = self._conn.execute(
                "SELECT 1 FROM observations WHERE observation_id = ?", [row[0]]
            ).fetchone()
            if exists:
                continue
            self._conn.execute(
                f"INSERT INTO observations VALUES ({', '.join('?' * len(_COLUMNS))})", list(row)
            )
            added += 1
        return added

    def count(self) -> int:
        return self._conn.execute("SELECT count(*) FROM observations").fetchone()[0]

    def as_of(self, decision_time: datetime) -> AsOfView:
        return AsOfView(self, decision_time)

    def unsafe_all(self, instrument_id: str, field: str) -> list[Observation]:
        """Every row regardless of availability. For audits and leak fixtures only."""
        rows = self._conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM observations WHERE instrument_id = ? AND field = ? "
            "ORDER BY event_time, vintage",
            [instrument_id, field],
        ).fetchall()
        return [_from_row(r) for r in rows]

    def export_parquet(self, path: str | Path) -> None:
        self._conn.execute(f"COPY observations TO '{Path(path).as_posix()}' (FORMAT PARQUET)")
