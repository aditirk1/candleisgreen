"""Follow-the-sun scheduling (spec Global markets and decision Q13).

Four slots a day, in UTC: Asia-Pacific, Europe, US, then an overnight review. Each slot runs
its jobs, each job is safe to rerun, and each writes a heartbeat. `run_week` drives the same
job table through seven simulated days for the Phase 6 acceptance test. `serve` runs it on
APScheduler 3.x for real. Orders are never placed by a scheduled job: the US slot records data
and makes the decision, and execution stays a separate, risk-checked step.
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


def _global_factors(now, workdir, cfg, fake):
    from .global_research import refresh_global_factors

    return refresh_global_factors(workdir, now, cfg, fake)


def _review(now, workdir, cfg, fake):
    from .core.audit import AuditLog
    from .research import factory
    from .research.registry import ResearchRegistry

    reg = ResearchRegistry(workdir / "research.sqlite", AuditLog(workdir / "audit.sqlite"))
    try:
        digest = factory.run_daily([], reg, factory.Library({}, {}), set(), cfg, now)
        return {"digest_date": digest["date"], "open_cases": len(reg.reevaluations("OPEN"))}
    finally:
        reg.close()


def _preopen(now, workdir, cfg, fake):
    from . import preopen

    return preopen.scheduled(now, workdir, cfg, fake)


JOBS: dict[str, list[tuple[str, Job]]] = {
    "us_preopen": [("preopen", _preopen)],
    "asia_pacific": [("global_factors", _global_factors)],
    "europe": [("fx", _fx)],
    "us": [("record", _record)],
    "overnight_review": [("review", _review)],
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

    out.append((local_to_utc(day, cfg.time.preopen_check_local, cfg.time.market_timezone), "us_preopen"))
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
    h, m = (int(x) for x in cfg.time.preopen_check_local.split(":"))
    sched.add_job(lambda: run_slot("us_preopen", datetime.now(UTC), workdir, cfg, fake), "cron", hour=h, minute=m,
                  timezone=cfg.time.market_timezone, id="us_preopen", coalesce=True, misfire_grace_time=1200)
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
