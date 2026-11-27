"""Scheduled trading-day operations, all in New York time and all safe to rerun.

- `decide` at `time.decision_time_local`: the Level A decision for the next session, then the daily
  Composite run, then shadow tracking for any signal at Tier 4.
- `execute` at `time.execution_window_start_local`: approved proposals (all proposals in an auto
  mode) go through the risk service to the simulator or the Alpaca paper account.
- `expire` at `time.execution_window_end_local`: proposals never approved expire.

No live venue exists. The paper broker refuses any host but Alpaca's paper endpoint, and every order
goes through the separate risk service, which fails closed when it cannot be reached.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .calendars import is_trading_day
from .core.audit import AuditLog
from .core.config import AppConfig
from .core.schemas import Venue
from .core.timeutil import ensure_utc, local_to_utc
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore
from .journal import Journal

NO_ORDER_MODES = ("research", "teaching")


def _local_date(now: datetime, cfg: AppConfig) -> date:
    return ensure_utc(now).astimezone(ZoneInfo(cfg.time.market_timezone)).date()


def next_session(day: date) -> date:
    d = day + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def _journal(workdir: Path, cfg: AppConfig) -> Journal:
    return Journal(workdir / "journal.sqlite", AuditLog(workdir / "audit.sqlite"), cfg.execution.simulator_starting_equity_usd,
                   f"config:{cfg.config_version}:{cfg.config_hash}")


def _effective_limits(cfg: AppConfig):
    """Limits as the risk service holds them, including Aditi's changes. Config values if it is unreachable,
    which only matters for what gets proposed: the risk service still checks every order."""
    from .core.config import HardLimits
    from .risk.client import RiskClient
    try:
        view = RiskClient(cfg.execution.risk_service_url, timeout=2.0)._call("GET", "/limits")
        return HardLimits.model_validate(view["effective"])
    except Exception:
        return cfg.risk.hard_limits


def decide(now: datetime, workdir: Path, cfg: AppConfig, fake: bool) -> dict:
    from .trading import run_decision

    day = _local_date(now, cfg)
    if not is_trading_day(day):
        return {"ran": False, "reason": f"{day} is not a trading day"}
    if cfg.execution.mode in NO_ORDER_MODES:
        return {"ran": False, "reason": f"mode {cfg.execution.mode} makes no proposals"}
    session = next_session(day)
    store = PointInTimeStore(workdir / "pit.duckdb")
    journal = _journal(workdir, cfg)
    try:
        master = InstrumentMaster(store.connection)
        res = run_decision(day, session, store, master, journal, cfg, now, limits=_effective_limits(cfg))
        composite = _composite(store, master, workdir, cfg, day, session, now)
    finally:
        journal.close()
        store.close()
    return {"ran": True, "decision_date": day.isoformat(), "session_date": session.isoformat(),
            "forecasts": res.forecasts, "proposals": len(res.proposal_ids),
            "composite": composite}


def _composite(store, master, workdir: Path, cfg: AppConfig, day: date, session: date, now: datetime) -> dict:
    """Daily Composite run, then shadow books for Tier 4 signals. The Composite places no orders."""
    from .composite.v0 import build
    from .research.registry import ResearchRegistry
    from .research.shadow import ShadowBook

    registry = ResearchRegistry(workdir / "research.sqlite", AuditLog(workdir / "audit.sqlite"))
    book = ShadowBook(workdir / "shadow.sqlite", cfg)
    try:
        record = build(store, master, registry, cfg, day, now)
        if record.get("status") == "NOT AVAILABLE":
            return {"status": "NOT AVAILABLE", "reason": record["reason"]}
        as_of = datetime.fromisoformat(record["as_of"])
        start = local_to_utc(session, "09:30", cfg.time.market_timezone)
        shadowed = []
        for sig in record["signals"]:
            if sig.get("tier", 0) < 4:
                continue
            sid = sig["signal_id"]
            p = sig.get("platform") or {}
            book.register(sid, p.get("mean_annual", 0.0), p.get("se_annual", 1.0), now)
            contrib = {sym: c.get(sid, 0.0) for sym, c in record["contributions"].items()}
            gross = sum(abs(v) for v in contrib.values())
            if gross > 0:
                weights = {master.instrument_for_symbol(s) or s: v / gross for s, v in contrib.items() if v}
                book.record_targets(sid, as_of, now, start, weights)
            shadowed.append(sid)
        book.mark(store, now)
        evaluations = [book.evaluate(sid, registry, now) for sid in book.registered()]
        return {"run_id": record["composite_run_id"], "unallocated_weight": record["unallocated_weight"],
                "shadowed": shadowed,
                "promotion_proposals": [e["proposal_id"] for e in evaluations if e.get("proposal_id")]}
    finally:
        book.close()
        registry.close()


def execute(now: datetime, workdir: Path, cfg: AppConfig, fake: bool, risk=None, broker=None, quotes=None) -> dict:
    from .broker.simulator import InternalSimulator
    from .risk.client import RiskClient
    from .sources.alpaca_quotes import AlpacaQuotes
    from .trading import execute_session

    day = _local_date(now, cfg)
    if not is_trading_day(day):
        return {"ran": False, "reason": f"{day} is not a trading day"}
    mode = cfg.execution.mode
    if mode in NO_ORDER_MODES:
        return {"ran": False, "reason": f"mode {mode} places no orders"}
    store = PointInTimeStore(workdir / "pit.duckdb", read_only=True)
    journal = _journal(workdir, cfg)
    try:
        master = InstrumentMaster.reader(store.connection)
        if fake:
            from .sources.alpaca_fake import FakeAlpacaTransport
            transport = FakeAlpacaTransport(now=now)
        else:
            from .sources.alpaca import HttpTransport
            transport = HttpTransport(cfg.sources.alpaca)
        quotes = quotes or AlpacaQuotes(transport, cfg.sources.alpaca)
        venue = Venue.PAPER if mode.startswith("broker_paper") else Venue.SIMULATION
        if broker is None:
            if venue is Venue.SIMULATION:
                broker = InternalSimulator(journal.cash(), journal.positions())
            elif fake:
                from .broker.alpaca_paper_fake import FakeAlpacaPaper
                broker = FakeAlpacaPaper(now=now)
            else:
                from .broker.alpaca_paper import AlpacaPaperBroker

                def symbol_for(iid):
                    syms = master.symbols(iid)
                    return syms[-1] if syms else None
                broker = AlpacaPaperBroker(transport, cfg.sources.alpaca, symbol_for, master.instrument_for_symbol)
        risk = risk or RiskClient(cfg.execution.risk_service_url)
        res = execute_session(day, now, journal, quotes, risk, broker, store, master, cfg, venue=venue)
    finally:
        journal.close()
        store.close()
    return {"ran": True, "session_date": day.isoformat(), "venue": venue.value, "submitted": len(res.submitted),
            "blocked": len(res.blocked)}


def expire(now: datetime, workdir: Path, cfg: AppConfig, fake: bool) -> dict:
    from .trading import expire_unapproved

    day = _local_date(now, cfg)
    if not is_trading_day(day):
        return {"ran": False, "reason": f"{day} is not a trading day"}
    journal = _journal(workdir, cfg)
    try:
        return {"ran": True, "expired": expire_unapproved(journal, day, ensure_utc(now))}
    finally:
        journal.close()
