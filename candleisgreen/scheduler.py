"""Follow-the-sun scheduling (spec Global markets and decision Q13).

Four research slots a day in UTC (Asia-Pacific, Europe, US, overnight review), plus four US trading
slots in New York time so they move with daylight saving: pre-open check, execution at the window
start, expiry at the window end, and the decision after the close. Each job is safe to rerun and
writes a heartbeat. `run_week` drives the same table through seven simulated days. `serve` runs it
on APScheduler 3.x. Execution sends paper or simulator orders only, each through the separate risk
service, and only approved proposals unless the mode is an auto mode.
"""
from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .core.config import AppConfig, load_config
from .jobs import write_heartbeat

UTC = timezone.utc
Job = Callable[[datetime, Path, AppConfig, bool], dict]


def _record(now, workdir, cfg, fake):
    from . import jobs

    return jobs.run("catch-up", workdir, fake, now, cfg)


def _fx(now, workdir, cfg, fake):
    from .global_research import refresh_fx

    return refresh_fx(workdir, now, fake)


def _macro(now, workdir, cfg, fake):
    from .global_research import refresh_macro

    return refresh_macro(workdir, now, cfg, fake)


def _ownership(now, workdir, cfg, fake):
    """Form 4 and large-holder filings for tracked SEC issuers, and 13F filings for listed managers. Research only."""
    if fake:
        return {"ran": False, "reason": "the synthetic market has no SEC issuers"}
    from .data.pit_store import PointInTimeStore
    from .sources import ownership, sec
    try:
        client = sec.SecClient(sec.HttpSecTransport(cfg.sources.sec), cfg.sources.sec)
    except sec.MissingUserAgentError as exc:
        return {"ran": False, "status": "NOT AVAILABLE", "reason": str(exc)}
    store = PointInTimeStore(workdir / "pit.duckdb")
    try:
        ciks = [r[0] for r in store.connection.execute("SELECT cik FROM issuers").fetchall()]
        insiders = sum(ownership.ingest_insiders(client, c, store.connection, limit=10)["transactions_added"] for c in ciks)
        managers = [ownership.ingest_13f(client, m, store.connection) for m in cfg.sources.sec.managers_13f]
    finally:
        store.close()
    return {"ran": True, "issuers": len(ciks), "insider_transactions_added": insiders, "managers": len(managers)}


def _trials(now, workdir, cfg, fake):
    from .global_research import refresh_trials

    return refresh_trials(workdir, now, cfg, fake)


def _global_factors(now, workdir, cfg, fake):
    from .global_research import refresh_global_factors

    return refresh_global_factors(workdir, now, cfg, fake)


def _review(now, workdir, cfg, fake):
    from .core.audit import AuditLog
    from .research import factory
    from .research.registry import ResearchRegistry

    from .research.inbox import Inbox

    reg = ResearchRegistry(workdir / "research.sqlite", AuditLog(workdir / "audit.sqlite"))
    inbox = Inbox(workdir / "inbox.sqlite", cfg.research.inbox)
    try:
        cards = inbox.take_for_factory()
        digest = factory.run_daily(cards, reg, factory.Library({}, {}), set(), cfg, now)
        return {"digest_date": digest["date"], "open_cases": len(reg.reevaluations("OPEN")), "captured_claims": len(cards)}
    finally:
        reg.close()
        inbox.close()


def _clusters(now, workdir, cfg, fake):
    from . import clusters
    from .data.instruments import InstrumentMaster
    from .data.pit_store import PointInTimeStore

    store = PointInTimeStore(workdir / "pit.duckdb")
    try:
        r = clusters.run(now, store, InstrumentMaster(store.connection), cfg)
        return {"run_id": r.run_id, "status": r.status, "names": len(r.labels), "stability": r.stability}
    finally:
        store.close()


def _decide(now, workdir, cfg, fake):
    from . import operations

    return operations.decide(now, workdir, cfg, fake)


def _execute(now, workdir, cfg, fake):
    from . import operations

    return operations.execute(now, workdir, cfg, fake)


def _expire(now, workdir, cfg, fake):
    from . import operations

    return operations.expire(now, workdir, cfg, fake)


def _preopen(now, workdir, cfg, fake):
    from . import preopen

    return preopen.scheduled(now, workdir, cfg, fake)


JOBS: dict[str, list[tuple[str, Job]]] = {
    "us_preopen": [("preopen", _preopen)],
    "us_execution": [("execute", _execute)],
    "us_expiry": [("expire", _expire)],
    "us_decision": [("decide", _decide)],
    "asia_pacific": [("global_factors", _global_factors)],
    "europe": [("fx", _fx), ("macro", _macro)],
    "us": [("record", _record)],
    "overnight_review": [("review", _review), ("clusters", _clusters), ("trials", _trials), ("ownership", _ownership)],
}


@dataclass
class WeekReport:
    runs: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    manual_steps: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures and self.manual_steps == 0


def slot_times(day: date, cfg: AppConfig) -> list[tuple[datetime, str]]:
    out = []
    for slot, hhmm in cfg.markets.sessions_utc.items():
        h, m = (int(x) for x in hhmm.split(":"))
        out.append((datetime.combine(day, time(h, m), tzinfo=UTC), slot))
    # The pre-open check follows New York local time, so it moves with daylight saving.
    from .core.timeutil import local_to_utc

    tz = cfg.time.market_timezone
    out.append((local_to_utc(day, cfg.time.preopen_check_local, tz), "us_preopen"))
    out.append((local_to_utc(day, cfg.time.execution_window_start_local, tz), "us_execution"))
    out.append((local_to_utc(day, cfg.time.execution_window_end_local, tz), "us_expiry"))
    out.append((local_to_utc(day, cfg.time.decision_time_local, tz), "us_decision"))
    return sorted(out)


def run_slot(slot: str, now: datetime, workdir: Path, cfg: AppConfig, fake: bool, report: Optional[WeekReport] = None) -> list[dict]:
    results = []
    for name, job in JOBS[slot]:
        try:
            out = job(now, workdir, cfg, fake)
            write_heartbeat(workdir / "heartbeats" / name, name, "ok", now, {"slot": slot})
            results.append({"slot": slot, "job": name, "at": now.isoformat(), "ok": True, "detail": out})
        except Exception as exc:
            write_heartbeat(workdir / "heartbeats" / name, name, "failed", now, {"error": f"{type(exc).__name__}: {exc}"})
            results.append({"slot": slot, "job": name, "at": now.isoformat(), "ok": False,
                            "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=3)})
    if report is not None:
        report.runs += results
        report.failures += [r for r in results if not r["ok"]]
    return results


def run_week(start: date, workdir: Path, cfg: Optional[AppConfig] = None, fake: bool = True) -> WeekReport:
    cfg = cfg or load_config()
    report = WeekReport()
    for offset in range(7):
        for when, slot in slot_times(start + timedelta(days=offset), cfg):
            run_slot(slot, when, workdir, cfg, fake, report)
    return report


def serve(workdir: Path, fake: bool) -> None:  # pragma: no cover - long-running process
    from apscheduler.schedulers.blocking import BlockingScheduler

    cfg = load_config()
    sched = BlockingScheduler(timezone="UTC")
    for slot, hhmm in cfg.markets.sessions_utc.items():
        h, m = (int(x) for x in hhmm.split(":"))
        sched.add_job(lambda s=slot: run_slot(s, datetime.now(UTC), workdir, cfg, fake), "cron", hour=h, minute=m,
                      id=slot, coalesce=True, misfire_grace_time=3600)
    for slot, hhmm, grace in (("us_preopen", cfg.time.preopen_check_local, 1200),
                              ("us_execution", cfg.time.execution_window_start_local, 1200),
                              ("us_expiry", cfg.time.execution_window_end_local, 3600),
                              ("us_decision", cfg.time.decision_time_local, 3600)):
        h, m = (int(x) for x in hhmm.split(":"))
        sched.add_job(lambda s=slot: run_slot(s, datetime.now(UTC), workdir, cfg, fake), "cron", hour=h, minute=m,
                      timezone=cfg.time.market_timezone, id=slot, coalesce=True, misfire_grace_time=grace)
    sched.start()


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(description="Follow-the-sun jobs. Paper only. No orders.")
    parser.add_argument("command", choices=["serve", "week"])
    parser.add_argument("--workdir", default="var/live")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--start", default=None)
    args = parser.parse_args()
    if args.command == "serve":
        serve(Path(args.workdir), args.fake)
    else:
        rep = run_week(date.fromisoformat(args.start) if args.start else date.today(), Path(args.workdir), fake=args.fake)
        print(json.dumps({"ok": rep.ok, "runs": len(rep.runs), "failures": rep.failures}, default=str, indent=2))
