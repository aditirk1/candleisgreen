"""Instrument master, corporate actions and completeness flags (spec v3.2 decision Q1).

The forward record is survivorship-aware: rows are never deleted, inactive and delisted
securities stay, every symbol and status change is kept with its dates, and every day
records how complete its collection was.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

import duckdb

from ..core.ids import canonical_json, make_id
from ..core.timeutil import ensure_utc, from_micros, to_micros


def _first(rows: list):
    """First row or None. Results are always fetched in full, as DuckDB 2.0 requires."""
    return rows[0] if rows else None

_DDL = """
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id VARCHAR PRIMARY KEY, vendor VARCHAR NOT NULL, vendor_asset_id VARCHAR NOT NULL,
    name VARCHAR, security_type VARCHAR NOT NULL, type_inferred BOOLEAN NOT NULL,
    leveraged_or_inverse BOOLEAN NOT NULL, first_seen_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS symbol_history (
    instrument_id VARCHAR NOT NULL, symbol VARCHAR NOT NULL, exchange VARCHAR NOT NULL,
    first_seen_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL,
    PRIMARY KEY (instrument_id, symbol, exchange)
);
CREATE TABLE IF NOT EXISTS status_history (
    instrument_id VARCHAR NOT NULL, status VARCHAR NOT NULL, tradable BOOLEAN NOT NULL,
    observed_at BIGINT NOT NULL, PRIMARY KEY (instrument_id, status, observed_at)
);
CREATE TABLE IF NOT EXISTS corporate_actions (
    action_id VARCHAR PRIMARY KEY, vendor_action_id VARCHAR, action_type VARCHAR NOT NULL,
    instrument_id VARCHAR, symbol VARCHAR, effective_date DATE, ingested_at BIGINT NOT NULL,
    raw_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS issuers (
    cik VARCHAR PRIMARY KEY, instrument_id VARCHAR NOT NULL, ticker VARCHAR, mapped_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS classifications (
    record_id VARCHAR PRIMARY KEY, instrument_id VARCHAR NOT NULL, cik VARCHAR, sic_code INTEGER,
    industry_ff12 VARCHAR NOT NULL, status VARCHAR NOT NULL, classified_at BIGINT NOT NULL,
    source_filing VARCHAR, mapping_version VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS completeness (
    record_id VARCHAR PRIMARY KEY, session_date DATE NOT NULL, source VARCHAR NOT NULL,
    session_open BOOLEAN NOT NULL, asset_list_snapshot_taken BOOLEAN NOT NULL,
    snapshot_taken_at BIGINT, symbols_expected INTEGER NOT NULL, bars_received INTEGER NOT NULL,
    missing_symbols VARCHAR NOT NULL, collection_mode VARCHAR NOT NULL, collected_at BIGINT NOT NULL
);
"""

_ETF = re.compile(r"\b(ETF|ETN|FUND|TRUST|SHARES)\b", re.I)
_LEVERAGED = re.compile(r"\b(2X|3X|-1X|-2X|-3X|ULTRA|ULTRAPRO|INVERSE|BEAR|SHORT|LEVERAGED)\b", re.I)


def infer_security_type(name: str) -> tuple[str, bool]:
    """Alpaca gives no security type, so it is inferred from the name and labeled inferred."""
    name = name or ""
    return ("etf" if _ETF.search(name) else "common_stock"), _LEVERAGED.search(name) is not None


def instrument_id_for(vendor: str, vendor_asset_id: str) -> str:
    return make_id("inst", {"vendor": vendor, "asset_id": vendor_asset_id})


@dataclass(frozen=True)
class CompletenessRecord:
    session_date: date
    source: str
    session_open: bool
    asset_list_snapshot_taken: bool
    snapshot_taken_at: Optional[datetime]
    symbols_expected: int
    bars_received: int
    missing_symbols: tuple[str, ...]
    collection_mode: str
    collected_at: datetime

    @property
    def record_id(self) -> str:
        return make_id("cmp", {k: getattr(self, k) for k in self.__dataclass_fields__})


class InstrumentMaster:
    def __init__(self, conn: duckdb.DuckDBPyConnection, vendor: str = "alpaca"):
        self.conn = conn
        self.vendor = vendor
        self._exec(_DDL)

    @classmethod
    def reader(cls, conn: duckdb.DuckDBPyConnection, vendor: str = "alpaca") -> "InstrumentMaster":
        """For a read-only store: skips table creation. Write methods then fail."""
        m = cls.__new__(cls)
        m.conn, m.vendor = conn, vendor
        return m

    def _exec(self, sql: str, args: Optional[list] = None) -> None:
        """Run a write statement and consume its result, as DuckDB 2.0 requires."""
        self.conn.execute(sql, args or []).fetchall()

    # Snapshots -----------------------------------------------------------------------------

    def apply_snapshot(self, assets: Iterable[dict], taken_at: datetime) -> dict[str, str]:
        """Record one asset-list snapshot. Returns symbol to instrument_id for this snapshot."""
        ts = to_micros(ensure_utc(taken_at))
        mapping: dict[str, str] = {}
        for a in assets:
            iid = instrument_id_for(self.vendor, a["id"])
            mapping[a["symbol"]] = iid
            sec_type, lev = infer_security_type(a.get("name", ""))
            self._exec(
                "INSERT INTO instruments VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                [iid, self.vendor, a["id"], a.get("name"), sec_type, True, lev, ts])
            self._exec(
                "INSERT INTO symbol_history VALUES (?,?,?,?,?) ON CONFLICT (instrument_id, symbol, exchange) "
                "DO UPDATE SET first_seen_at = least(symbol_history.first_seen_at, excluded.first_seen_at), "
                "last_seen_at = greatest(symbol_history.last_seen_at, excluded.last_seen_at)",
                [iid, a["symbol"], a.get("exchange", ""), ts, ts])
            last = _first(self.conn.execute(
                "SELECT status, tradable FROM status_history WHERE instrument_id = ? ORDER BY observed_at DESC LIMIT 1",
                [iid]).fetchall())
            current = (a.get("status", "active"), bool(a.get("tradable", False)))
            if last is None or tuple(last) != current:
                self._exec("INSERT INTO status_history VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                                  [iid, current[0], current[1], ts])
        return mapping

    def mark_delisted(self, instrument_id: str, observed_at: datetime) -> None:
        self._exec("INSERT INTO status_history VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                          [instrument_id, "delisted", False, to_micros(ensure_utc(observed_at))])

    # Lookups -------------------------------------------------------------------------------

    def instrument_for_symbol(self, symbol: str) -> Optional[str]:
        row = _first(self.conn.execute(
            "SELECT instrument_id FROM symbol_history WHERE symbol = ? ORDER BY last_seen_at DESC, first_seen_at DESC LIMIT 1",
            [symbol]).fetchall())
        return row[0] if row else None

    def symbols(self, instrument_id: str) -> list[str]:
        rows = self.conn.execute("SELECT symbol FROM symbol_history WHERE instrument_id = ? ORDER BY first_seen_at",
                                 [instrument_id]).fetchall()
        return [r[0] for r in rows]

    def status(self, instrument_id: str) -> Optional[str]:
        """Latest status. A delisting outranks a snapshot taken at the same moment."""
        row = _first(self.conn.execute(
            "SELECT status FROM status_history WHERE instrument_id = ? "
            "ORDER BY observed_at DESC, (status = 'delisted') DESC LIMIT 1", [instrument_id]).fetchall())
        return row[0] if row else None

    def tag(self, instrument_id: str, us_exchanges: tuple[str, ...]) -> str:
        """direct: a US listing with market data. proxy: a US-listed ADR or fund on foreign exposure.
        research_only: everything else, every non-US instrument included."""
        inst = _first(self.conn.execute("SELECT vendor, name FROM instruments WHERE instrument_id = ?",
                                        [instrument_id]).fetchall())
        if inst is None or inst[0] != "alpaca":
            return "research_only"
        ex = _first(self.conn.execute("SELECT exchange FROM symbol_history WHERE instrument_id = ? "
                                      "ORDER BY last_seen_at DESC LIMIT 1", [instrument_id]).fetchall())
        if ex is None or ex[0].upper() not in us_exchanges:
            return "research_only"
        name = (inst[1] or "").upper()
        return "proxy" if ("ADR" in name.split() or "DEPOSITARY" in name) else "direct"

    def instruments(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM instruments ORDER BY instrument_id")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def count(self, table: str) -> int:
        if table not in ("instruments", "symbol_history", "status_history", "corporate_actions", "completeness",
                         "issuers", "classifications"):
            raise ValueError(table)
        return _first(self.conn.execute(f"SELECT count(*) FROM {table}").fetchall())[0]

    # Corporate actions ---------------------------------------------------------------------

    def add_actions(self, actions: dict[str, list[dict]], ingested_at: datetime) -> int:
        added = 0
        ts = to_micros(ensure_utc(ingested_at))
        for kind, rows in actions.items():
            for row in rows:
                symbol = row.get("symbol") or row.get("old_symbol")
                iid = self.instrument_for_symbol(symbol) or (
                    self.instrument_for_symbol(row["new_symbol"]) if row.get("new_symbol") else None)
                eff = row.get("ex_date") or row.get("process_date") or row.get("effective_date")
                aid = make_id("act", {"kind": kind, "raw": row})
                before = self.count("corporate_actions")
                self._exec("INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                                  [aid, row.get("id"), kind, iid, symbol, eff, ts, canonical_json(row)])
                if kind == "worthless_removals" and iid:
                    self.mark_delisted(iid, ingested_at)
                if kind == "name_changes" and iid and row.get("old_symbol"):
                    self._add_old_symbol(iid, row["old_symbol"], ts)
                added += self.count("corporate_actions") - before
        return added

    def _add_old_symbol(self, instrument_id: str, old_symbol: str, ts: int) -> None:
        """A ticker change keeps one instrument_id. The old symbol joins its history."""
        row = _first(self.conn.execute("SELECT exchange FROM symbol_history WHERE instrument_id = ? LIMIT 1",
                                [instrument_id]).fetchall())
        self._exec("INSERT INTO symbol_history VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                          [instrument_id, old_symbol, row[0] if row else "", ts, ts])

    def actions(self, instrument_id: Optional[str] = None) -> list[dict]:
        sql = "SELECT action_type, symbol, effective_date, raw_json FROM corporate_actions"
        args: list = []
        if instrument_id:
            sql += " WHERE instrument_id = ?"
            args = [instrument_id]
        rows = self.conn.execute(sql + " ORDER BY effective_date", args).fetchall()
        return [{"action_type": r[0], "symbol": r[1], "effective_date": r[2], "raw": json.loads(r[3])} for r in rows]

    # Issuers and classifications -----------------------------------------------------------

    def map_issuer(self, cik: str, ticker: Optional[str], mapped_at: datetime) -> str:
        """Link an SEC issuer to an instrument. Falls back to a CIK-based ID when no ticker matches."""
        row = _first(self.conn.execute("SELECT instrument_id FROM issuers WHERE cik = ?", [cik]).fetchall())
        if row:
            return row[0]
        iid = (self.instrument_for_symbol(ticker) if ticker else None) or make_id("inst", {"vendor": "sec", "cik": cik})
        self._exec("INSERT INTO issuers VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                   [cik, iid, ticker, to_micros(ensure_utc(mapped_at))])
        return iid

    def add_classification(self, instrument_id: str, cik: Optional[str], sic_code: Optional[int], industry: str,
                           status: str, classified_at: datetime, source_filing: Optional[str], mapping_version: str) -> None:
        rid = make_id("cls", {"iid": instrument_id, "sic": sic_code, "ind": industry, "status": status,
                              "at": classified_at, "ver": mapping_version})
        self._exec("INSERT INTO classifications VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                   [rid, instrument_id, cik, sic_code, industry, status, to_micros(ensure_utc(classified_at)),
                    source_filing, mapping_version])

    def sector_at(self, instrument_id: str, when: datetime) -> str:
        """Industry known at `when`. Before the first classification it is UNKNOWN."""
        row = _first(self.conn.execute(
            "SELECT industry_ff12 FROM classifications WHERE instrument_id = ? AND classified_at <= ? "
            "ORDER BY classified_at DESC LIMIT 1", [instrument_id, to_micros(ensure_utc(when))]).fetchall())
        return row[0] if row else "UNKNOWN"

    def classifications(self, instrument_id: str) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM classifications WHERE instrument_id = ? ORDER BY classified_at",
                                [instrument_id])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # Completeness --------------------------------------------------------------------------

    def add_completeness(self, rec: CompletenessRecord) -> bool:
        before = self.count("completeness")
        self._exec(
            "INSERT INTO completeness VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            [rec.record_id, rec.session_date, rec.source, rec.session_open, rec.asset_list_snapshot_taken,
             to_micros(rec.snapshot_taken_at) if rec.snapshot_taken_at else None, rec.symbols_expected,
             rec.bars_received, ",".join(rec.missing_symbols), rec.collection_mode, to_micros(rec.collected_at)])
        return self.count("completeness") > before

    def completeness(self, session_date: date, source: str = "alpaca") -> list[dict]:
        cur = self.conn.execute("SELECT * FROM completeness WHERE session_date = ? AND source = ? ORDER BY collected_at",
                                [session_date, source])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def last_complete_session(self, source: str = "alpaca") -> Optional[date]:
        row = _first(self.conn.execute(
            "SELECT max(session_date) FROM completeness WHERE source = ? AND session_open", [source]).fetchall())
        return row[0] if row and row[0] else None

    def recorded_dates(self, source: str = "alpaca") -> set[date]:
        return {r[0] for r in self.conn.execute(
            "SELECT DISTINCT session_date FROM completeness WHERE source = ?", [source]).fetchall()}
