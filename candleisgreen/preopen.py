"""Pre-open check at 09:00 ET (spec C.1). It may cancel buy orders and can never add any.

A buy is cancelled when, since the decision time, its name was halted, had a corporate action
take effect, or filed an 8-K (earnings releases are 8-Ks). Sells are left alone, because they
reduce risk.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Iterable, Mapping, Optional

from .core.timeutil import ensure_utc
from .data.instruments import InstrumentMaster
from .journal import Journal

ACTOR = "system:preopen"


def run(session_date: date, now: datetime, decision_time: datetime, journal: Journal, master: InstrumentMaster,
        halted: Iterable[str], filings_since: Callable[[str, datetime], list[str]],
        unchecked: Optional[Mapping[str, str]] = None) -> list[dict]:
    """`unchecked` maps a symbol to the reason a check could not run. Those buys are cancelled too."""
    halted = set(halted)
    unchecked = dict(unchecked or {})
    cancelled = []
    for p in journal.proposals(session_date):
        if p.side != "buy" or p.status not in ("proposed", "approved"):
            continue
        reasons = []
        if p.symbol in halted:
            reasons.append("trading halt since the decision")
        if p.symbol in unchecked:
            reasons.append(unchecked[p.symbol])
        acts = [a for a in master.actions(p.instrument_id)
                if a["effective_date"] and decision_time.date() < a["effective_date"] <= session_date]
        if acts:
            reasons.append(f"corporate action effective {acts[0]['effective_date']}: {acts[0]['action_type']}")
        try:
            forms = [f for f in filings_since(p.instrument_id, decision_time) if f.startswith("8-K")]
        except Exception as exc:  # a check that cannot run fails closed
            forms = []
            reasons.append(f"filings could not be checked ({type(exc).__name__})")
        if forms:
            reasons.append("8-K filed since the decision")
        if reasons:
            journal.set_status(p.proposal_id, "cancelled", ACTOR, ensure_utc(now), "pre-open check: " + ", ".join(reasons))
            cancelled.append({"proposal_id": p.proposal_id, "symbol": p.symbol, "reasons": reasons})
    return cancelled


def previous_session(day: date) -> date:
    from datetime import timedelta

    from .calendars import is_trading_day

    d = day - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def sec_filings_lookup(master: InstrumentMaster, client) -> Callable[[str, datetime], list[str]]:
    """Forms accepted since a time, for instruments with a known CIK. ETFs and unmapped names return none."""
    from .sources.sec import filing_index

    def lookup(instrument_id: str, since: datetime) -> list[str]:
        rows = master.conn.execute("SELECT cik FROM issuers WHERE instrument_id = ?", [instrument_id]).fetchall()
        if not rows:
            return []
        if client is None:
            raise RuntimeError("no SEC client")
        out = []
        for f in filing_index(client.submissions(rows[0][0])).values():
            acc = f.get("acceptance")
            if acc and ensure_utc(datetime.fromisoformat(acc.replace("Z", "+00:00"))) >= ensure_utc(since):
                out.append(f["form"])
        return out
    return lookup


def scheduled(now: datetime, workdir, cfg, fake: bool, assets_source=None, sec_client=None) -> dict:
    """The 09:00 ET job. Reads asset status and recent filings, then cancels risky buys.

    If asset status cannot be read, every buy for the session is cancelled. Nothing is ever added.
    """
    from pathlib import Path

    from .calendars import is_trading_day
    from .core.audit import AuditLog
    from .core.timeutil import local_to_utc
    from .data.pit_store import PointInTimeStore
    from zoneinfo import ZoneInfo

    workdir = Path(workdir)
    tz = cfg.time.market_timezone
    session = ensure_utc(now).astimezone(ZoneInfo(tz)).date()
    if not is_trading_day(session):
        return {"session": session.isoformat(), "ran": False, "reason": "not a trading day"}
    decision_time = local_to_utc(previous_session(session), cfg.time.decision_time_local, tz)
    audit = AuditLog(workdir / "audit.sqlite")
    journal = Journal(workdir / "journal.sqlite", audit, cfg.execution.simulator_starting_equity_usd,
                      f"config:{cfg.config_version}:{cfg.config_hash}")
    store = PointInTimeStore(workdir / "pit.duckdb", read_only=True)
    try:
        master = InstrumentMaster.reader(store.connection)
        buys = {p.symbol for p in journal.proposals(session) if p.side == "buy" and p.status in ("proposed", "approved")}
        halted, unchecked = set(), {}
        try:
            if assets_source is None:
                from .jobs import _data

                assets_source = _data(cfg, fake, now)
            for a in assets_source.assets("active"):
                if not a.get("tradable", False):
                    halted.add(a["symbol"])
            listed = {a["symbol"] for a in assets_source.assets("active")}
            halted |= {s for s in buys if s not in listed}
        except Exception as exc:
            unchecked = {s: f"asset status could not be checked ({type(exc).__name__})" for s in buys}
        if sec_client is None and not fake:
            try:
                from .sources.sec import HttpSecTransport, SecClient

                sec_client = SecClient(HttpSecTransport(cfg.sources.sec), cfg.sources.sec)
            except Exception:
                sec_client = None  # lookups for SEC filers then fail closed
        lookup = sec_filings_lookup(master, sec_client) if (sec_client is not None or not fake) else (lambda i, s: [])
        cancelled = run(session, now, decision_time, journal, master, halted, lookup, unchecked)
        return {"session": session.isoformat(), "ran": True, "checked": len(buys), "cancelled": cancelled,
                "filings": "checked" if sec_client is not None else ("not checked in the synthetic market" if fake else "no SEC client")}
    finally:
        store.close()
        journal.close()
