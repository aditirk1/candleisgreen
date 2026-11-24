"""Scheduled jobs (spec decision Q13). Every job is safe to rerun and catches up after a gap.

Oracle Cloud Always Free runs these on a schedule. The same commands run on Aditi's
computer as the fallback: `fallback` checks the heartbeat and runs `catch-up` when the
cloud run is missing. No artificial load is generated to avoid Oracle's idle rule.

    python -m candleisgreen.jobs record   --workdir var/live [--fake]
    python -m candleisgreen.jobs catch-up --workdir var/live [--fake]
    python -m candleisgreen.jobs fallback --workdir var/live [--fake]
    python -m candleisgreen.jobs heartbeat --workdir var/live
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .core.config import AppConfig, load_config
from .core.timeutil import ensure_utc, local_to_utc, utc_now
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore
from .sources import recorder
from .sources.alpaca import AlpacaData, HttpTransport, TooEarlyError

HEARTBEAT = "heartbeat.json"


def write_heartbeat(workdir: Path, job: str, status: str, now: datetime, detail: dict) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / HEARTBEAT).write_text(json.dumps(
        {"job": job, "status": status, "finished_at": ensure_utc(now).isoformat(), **detail}, default=str))


def read_heartbeat(workdir: Path) -> Optional[dict]:
    path = workdir / HEARTBEAT
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def heartbeat_stale(workdir: Path, now: datetime, max_age_hours: float) -> bool:
    beat = read_heartbeat(workdir)
    if beat is None or beat.get("status") != "ok":
        return True
    age = ensure_utc(now) - datetime.fromisoformat(beat["finished_at"])
    return age > timedelta(hours=max_age_hours)


def last_collectable_session(now: datetime, cfg: AppConfig) -> date:
    """Most recent date whose close plus the free-plan delay has passed."""
    tz = cfg.time.market_timezone
    day = ensure_utc(now).astimezone(ZoneInfo(tz)).date()
    ready = local_to_utc(day, cfg.sources.recorder.close_time_local, tz) + timedelta(minutes=cfg.sources.alpaca.sip_delay_minutes)
    return day if ensure_utc(now) >= ready else day - timedelta(days=1)


def catch_up(data: AlpacaData, store: PointInTimeStore, master: InstrumentMaster, now: datetime, cfg: AppConfig,
             start: Optional[date] = None) -> list[date]:
    """Record every weekday from the day after the last recorded one up to today."""
    end = last_collectable_session(now, cfg)
    recorded = master.recorded_dates()
    first = start or ((max(recorded) + timedelta(days=1)) if recorded else end)
    done = []
    day = first
    while day <= end:
        if day.weekday() < 5 and day not in recorded:
            try:
                recorder.record_session(day, data, store, master, now, cfg)
                done.append(day)
            except TooEarlyError:
                break
        day += timedelta(days=1)
    return done


def _data(cfg: AppConfig, fake: bool, now: datetime) -> AlpacaData:
    if fake:
        from .sources.alpaca_fake import FakeAlpacaTransport

        return AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca, cfg.sources.recorder.close_time_local)
    return AlpacaData(HttpTransport(cfg.sources.alpaca), cfg.sources.alpaca, cfg.sources.recorder.close_time_local)


def run(job: str, workdir: Path, fake: bool, now: Optional[datetime] = None, cfg: Optional[AppConfig] = None) -> dict:
    cfg = cfg or load_config()
    now = ensure_utc(now or utc_now())
    if job == "heartbeat":
        return {"stale": heartbeat_stale(workdir, now, cfg.sources.recorder.heartbeat_max_age_hours),
                "heartbeat": read_heartbeat(workdir)}
    if job == "fallback" and not heartbeat_stale(workdir, now, cfg.sources.recorder.heartbeat_max_age_hours):
        return {"ran": False, "reason": "heartbeat is fresh"}
    workdir.mkdir(parents=True, exist_ok=True)
    store = PointInTimeStore(workdir / "pit.duckdb")
    try:
        master = InstrumentMaster(store.connection)
        data = _data(cfg, fake, now)
        if job == "record":
            day = last_collectable_session(now, cfg)
            res = recorder.record_session(day, data, store, master, now, cfg)
            detail = {"sessions": [day.isoformat()], "observations_added": res.observations_added}
        elif job in ("catch-up", "fallback"):
            days = catch_up(data, store, master, now, cfg)
            detail = {"sessions": [d.isoformat() for d in days]}
        else:
            raise ValueError(f"unknown job {job}")
        write_heartbeat(workdir, job, "ok", now, detail)
        return {"ran": True, **detail}
    except Exception as exc:
        write_heartbeat(workdir, job, "failed", now, {"error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        store.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CandleIsGreen scheduled jobs. Paper only.")
    parser.add_argument("job", choices=["record", "catch-up", "fallback", "heartbeat"])
    parser.add_argument("--workdir", default="var/live")
    parser.add_argument("--fake", action="store_true", help="use the offline synthetic market")
    args = parser.parse_args(argv)
    out = run(args.job, Path(args.workdir), args.fake)
    print(json.dumps(out, default=str))
    return 1 if args.job == "heartbeat" and out["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
