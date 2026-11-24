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
import pyarrow as pa

from ..core.ids import make_id
from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc, from_micros, to_micros



def _first(rows: list):
    """First row or None. Results are always fetched in full, as DuckDB 2.0 requires."""
    return rows[0] if rows else None

class LookaheadError(RuntimeError):
    """An input was not usable at the decision time. This must fail the build."""


_TIME_COLS = ("event_time", "published_at", "vendor_available_at", "ingested_at", "first_usable_at")
_COLUMNS = (
    "observation_id", "instrument_id", "vendor", "raw_symbol", "exchange", "field", "value",
    *_TIME_COLS, "timezone", "currency", "adjustment_method", "vintage", "missing_flag",
    "license", "collection_mode", "source_ref",
)

_ARROW_SCHEMA = pa.schema([
    ("observation_id", pa.string()), ("instrument_id", pa.string()), ("vendor", pa.string()),
    ("raw_symbol", pa.string()), ("exchange", pa.string()), ("field", pa.string()), ("value", pa.float64()),
    *[(name, pa.int64()) for name in _TIME_COLS],
    ("timezone", pa.string()), ("currency", pa.string()), ("adjustment_method", pa.string()),
    ("vintage", pa.int32()), ("missing_flag", pa.bool_()), ("license", pa.string()), ("collection_mode", pa.string()),
    ("source_ref", pa.string()),
])

_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    observation_id VARCHAR PRIMARY KEY,
    instrument_id VARCHAR NOT NULL, vendor VARCHAR NOT NULL, raw_symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL, field VARCHAR NOT NULL, value DOUBLE,
    event_time BIGINT NOT NULL, published_at BIGINT NOT NULL, vendor_available_at BIGINT NOT NULL,
    ingested_at BIGINT NOT NULL, first_usable_at BIGINT NOT NULL,
    timezone VARCHAR NOT NULL, currency VARCHAR NOT NULL, adjustment_method VARCHAR NOT NULL,
    vintage INTEGER NOT NULL, missing_flag BOOLEAN NOT NULL, license VARCHAR NOT NULL,
    collection_mode VARCHAR NOT NULL, source_ref VARCHAR
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
    def __init__(self, path: str | Path = ":memory:", read_only: bool = False):
        self._conn = duckdb.connect(str(path), read_only=read_only)
        if not read_only:
            self._conn.execute(_DDL).fetchall()

    def close(self) -> None:
        self._conn.close()

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Shared with the instrument master so both live in one database file."""
        return self._conn

    def add(self, observations: Iterable[Observation]) -> int:
        """Append observations in one bulk insert. Returns the count of new rows. Duplicates are ignored."""
        rows: dict[str, tuple] = {}
        for obs in observations:
            row = _to_row(obs)
            rows.setdefault(row[0], row)
        if not rows:
            return 0
        columns = list(zip(*rows.values()))
        table = pa.table({name: list(values) for name, values in zip(_COLUMNS, columns)},
                         schema=_ARROW_SCHEMA)
        before = self.count()
        self._conn.register("_incoming", table)
        try:
            self._conn.execute(
                f"INSERT INTO observations SELECT {', '.join(_COLUMNS)} FROM _incoming ON CONFLICT DO NOTHING"
            ).fetchall()
        finally:
            self._conn.unregister("_incoming")
        return self.count() - before

    def count(self) -> int:
        return _first(self._conn.execute("SELECT count(*) FROM observations").fetchall())[0]

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
        self._conn.execute(f"COPY observations TO '{Path(path).as_posix()}' (FORMAT PARQUET)").fetchall()
