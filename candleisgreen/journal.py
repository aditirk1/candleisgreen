"""Trading journal: proposals, approvals, orders, fills and cash. SQLite, audited.

Every status change writes an audit record. Positions and cash are derived from fills, so
there is one source of truth. Nothing here talks to a broker.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .core.audit import AuditLog
from .core.sqlite_shared import connect as sqlite_connect
from .core.ids import make_id
from .core.schemas import Fill, OrderIntent, RiskDecision
from .core.timeutil import ensure_utc, iso_utc

STATUSES = ("proposed", "approved", "rejected", "blocked", "submitted", "filled", "partially_filled", "resting",
            "broker_rejected", "unknown", "expired", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY, decision_date TEXT NOT NULL, session_date TEXT NOT NULL,
    instrument_id TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL,
    forecast_id TEXT NOT NULL, model_id TEXT NOT NULL, model_version TEXT NOT NULL,
    signal_strength REAL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    client_order_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    fill_id TEXT PRIMARY KEY, client_order_id TEXT NOT NULL, instrument_id TEXT NOT NULL, side TEXT NOT NULL,
    quantity REAL NOT NULL, price REAL NOT NULL, venue TEXT NOT NULL, filled_at TEXT NOT NULL,
    slippage_bps REAL
);
CREATE TABLE IF NOT EXISTS account (
    key TEXT PRIMARY KEY, value REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_history (
    as_of TEXT PRIMARY KEY, equity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS marks (
    instrument_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, price REAL NOT NULL, as_of TEXT NOT NULL, source TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    decision_date: str
    session_date: str
    instrument_id: str
    symbol: str
    side: str
    quantity: float
    forecast_id: str
    model_id: str
    model_version: str
    signal_strength: Optional[float]
    status: str
    reason: str
    client_order_id: Optional[str]


class Journal:
    def __init__(self, path: str | Path, audit: AuditLog, starting_cash: float, strategy_version: str,
                 shared_across_threads: bool = False):
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)
        self.audit = audit
        self.strategy_version = strategy_version
        self.conn.execute("INSERT OR IGNORE INTO account VALUES ('starting_cash', ?)", (starting_cash,))

    def close(self) -> None:
        self.conn.close()

    def _log(self, event_type: str, entity_id: str, payload, actor: str, when: datetime) -> None:
        self.audit.append(event_type=event_type, entity_id=entity_id, payload=payload, actor=actor,
                          strategy_version=self.strategy_version, event_time=when, received_time=when)

    # Proposals -----------------------------------------------------------------------------

    def add_proposal(self, *, decision_date: date, session_date: date, instrument_id: str, symbol: str, side: str,
                     quantity: float, forecast_id: str, model_id: str, model_version: str,
                     signal_strength: Optional[float], now: datetime) -> str:
        pid = make_id("prop", {"decision_date": decision_date, "instrument_id": instrument_id, "side": side,
                               "quantity": quantity, "forecast_id": forecast_id})
        stamp = iso_utc(now)
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, decision_date.isoformat(), session_date.isoformat(), instrument_id, symbol, side, quantity,
             forecast_id, model_id, model_version, signal_strength, "proposed", "", None, stamp, stamp))
        if cur.rowcount:
            self._log("proposal_created", pid, {"symbol": symbol, "side": side, "quantity": quantity,
                                                "forecast_id": forecast_id}, "system:decision", now)
        return pid

    def proposal(self, pid: str) -> Proposal:
        row = self.conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (pid,)).fetchone()
        if row is None:
            raise KeyError(pid)
        return Proposal(*row[:14])

    def proposals(self, session_date: Optional[date] = None, status: Optional[str] = None) -> list[Proposal]:
        sql, args = "SELECT * FROM proposals WHERE 1=1", []
        if session_date:
            sql += " AND session_date = ?"
            args.append(session_date.isoformat())
        if status:
            sql += " AND status = ?"
            args.append(status)
        return [Proposal(*r[:14]) for r in self.conn.execute(sql + " ORDER BY created_at, symbol", args).fetchall()]

    def set_status(self, pid: str, status: str, actor: str, now: datetime, reason: str = "",
                   client_order_id: Optional[str] = None) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        self.conn.execute(
            "UPDATE proposals SET status = ?, reason = ?, client_order_id = coalesce(?, client_order_id), updated_at = ? "
            "WHERE proposal_id = ?", (status, reason, client_order_id, iso_utc(now), pid))
        self._log(f"proposal_{status}", pid, {"reason": reason, "client_order_id": client_order_id}, actor, now)

    def approve(self, pid: str, actor: str, now: datetime) -> None:
        if self.proposal(pid).status != "proposed":
            raise ValueError("only a proposed order can be approved")
        self.set_status(pid, "approved", actor, now)

    def reject(self, pid: str, actor: str, now: datetime, reason: str = "rejected by user") -> None:
        if self.proposal(pid).status not in ("proposed", "approved"):
            raise ValueError("only a proposed or approved order can be rejected")
        self.set_status(pid, "rejected", actor, now, reason)

    # Orders and fills ----------------------------------------------------------------------

    def record_risk(self, intent: OrderIntent, decision: RiskDecision, now: datetime) -> None:
        self._log("order_intent_created", intent.client_order_id, intent, "system:executor", now)
        self._log("risk_decision", decision.risk_decision_id, decision, "service:risk", now)

    def record_fill(self, fill: Fill) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO fills VALUES (?,?,?,?,?,?,?,?,?)",
            (fill.fill_id, fill.client_order_id, fill.asset_id, fill.side.value, fill.quantity, fill.price,
             fill.venue.value, iso_utc(fill.filled_at), fill.slippage_bps))
        if cur.rowcount:
            self._log("fill", fill.fill_id, fill, "broker:simulator", fill.filled_at)
        return bool(cur.rowcount)

    def fills(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM fills ORDER BY filled_at")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def positions(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for iid, side, qty in self.conn.execute("SELECT instrument_id, side, quantity FROM fills").fetchall():
            out[iid] = out.get(iid, 0.0) + (qty if side == "buy" else -qty)
        return {k: v for k, v in out.items() if abs(v) > 1e-9}

    def cash(self) -> float:
        start = self.conn.execute("SELECT value FROM account WHERE key = 'starting_cash'").fetchone()[0]
        flows = self.conn.execute(
            "SELECT coalesce(sum(CASE WHEN side = 'buy' THEN -quantity * price ELSE quantity * price END), 0) FROM fills"
        ).fetchone()[0]
        return float(start + flows)

    def pending_buys(self) -> dict[str, float]:
        """Quantity of submitted or resting buys not yet filled, per instrument."""
        out: dict[str, float] = {}
        for iid, qty in self.conn.execute(
                "SELECT instrument_id, quantity FROM proposals WHERE side = 'buy' "
                "AND status IN ('submitted', 'resting', 'partially_filled', 'unknown')"
        ).fetchall():
            out[iid] = out.get(iid, 0.0) + qty
        return out

    def record_reconciliation(self, matched: bool, mismatches, actor: str, now: datetime) -> None:
        self._log("reconciliation", "account", {"matched": matched, "mismatches": list(mismatches)}, actor, now)
        self.conn.execute("INSERT OR REPLACE INTO account VALUES ('last_reconciliation_matched', ?)", (1.0 if matched else 0.0,))

    def last_reconciliation(self) -> Optional[bool]:
        row = self.conn.execute("SELECT value FROM account WHERE key = 'last_reconciliation_matched'").fetchone()
        return None if row is None else bool(row[0])

    def record_equity(self, as_of: datetime, equity: float) -> None:
        self.conn.execute("INSERT OR REPLACE INTO equity_history VALUES (?, ?)", (iso_utc(as_of), equity))

    def record_mark(self, instrument_id: str, symbol: str, price: float, as_of: datetime, source: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO marks VALUES (?,?,?,?,?)",
                          (instrument_id, symbol, price, iso_utc(as_of), source))

    def marks(self) -> dict[str, dict]:
        cur = self.conn.execute("SELECT instrument_id, symbol, price, as_of, source FROM marks")
        return {r[0]: {"symbol": r[1], "price": r[2], "as_of": r[3], "source": r[4]} for r in cur.fetchall()}

    def equity_history(self) -> list[tuple[str, float]]:
        return list(self.conn.execute("SELECT as_of, equity FROM equity_history ORDER BY as_of").fetchall())
