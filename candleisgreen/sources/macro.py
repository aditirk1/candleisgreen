"""Macro series with every vintage, from the FRED API (spec Data sources: FRED and ALFRED).

`series/observations` with realtime_start=1776-07-04 and realtime_end=9999-12-31 returns each value
with the real-time period in which it was the published value. Each new real-time period for the same
observation date is a new vintage, so the point-in-time store answers "what was known then".

ALFRED gives release dates, not times. A value is treated as usable from
`sources.fred.release_time_local` on its realtime_start date, New York time. That is later than most
US releases, so it never makes a value usable before it was public.

The API key comes from the environment variable named in `sources.fred.api_key_env`. Without it the
job reports NOT AVAILABLE. The documentation page does not state the missing-value marker, so any
value that is not a number is stored as missing.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from ..core.config import FredSourceConfig
from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc

ALL_START, ALL_END = "1776-07-04", "9999-12-31"
VENDOR = "fred"


class MissingApiKeyError(RuntimeError):
    pass


class HttpFredTransport:
    def __init__(self, cfg: FredSourceConfig):
        self.key = os.environ.get(cfg.api_key_env)
        if not self.key:
            raise MissingApiKeyError(f"set {cfg.api_key_env} to a FRED API key")
        self.base = cfg.base_url.rstrip("/")

    def get(self, path: str, params: dict) -> Any:
        q = urllib.parse.urlencode({**params, "api_key": self.key, "file_type": "json"})
        with urllib.request.urlopen(f"{self.base}/{path}?{q}", timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class FixtureFredTransport:
    """Recorded responses: one JSON file per series in a directory. No network."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def get(self, path: str, params: dict) -> Any:
        data = json.loads((self.dir / f"{params['series_id']}.json").read_text())
        offset, limit = int(params.get("offset", 0)), int(params.get("limit", 100000))
        return {**data, "observations": data["observations"][offset:offset + limit]}


def all_vintages(transport, series_id: str, page: int = 100000) -> list[dict]:
    out, offset = [], 0
    while True:
        data = transport.get("series/observations", {"series_id": series_id, "realtime_start": ALL_START,
                                                     "realtime_end": ALL_END, "limit": page, "offset": offset})
        rows = data.get("observations", [])
        out += rows
        if len(rows) < page:
            return out
        offset += page


def _number(text: str) -> Optional[float]:
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def to_observations(series_id: str, rows: list[dict], cfg: FredSourceConfig, license_id: str,
                    now: datetime) -> list[Observation]:
    tz = ZoneInfo("America/New_York")
    hh, mm = (int(x) for x in cfg.release_time_local.split(":"))
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    out = []
    for d, versions in by_date.items():
        event = datetime.combine(date.fromisoformat(d), time(0), tzinfo=timezone.utc)
        for vintage, r in enumerate(sorted(versions, key=lambda x: x["realtime_start"])):
            known = datetime.combine(date.fromisoformat(r["realtime_start"]), time(hh, mm), tzinfo=tz).astimezone(timezone.utc)
            known = max(known, event)
            value = _number(r["value"])
            out.append(Observation(
                instrument_id=f"macro:{series_id}", vendor=VENDOR, raw_symbol=series_id, exchange="NONE", field="value",
                value=value, event_time=event, published_at=known, vendor_available_at=known, ingested_at=ensure_utc(now),
                first_usable_at=known, timezone="America/New_York", currency="NONE", adjustment_method="none",
                vintage=vintage, missing_flag=value is None, license=license_id, collection_mode=CollectionMode.BACKFILL,
                source_ref=f"FRED series/observations {series_id} realtime {r['realtime_start']} to {r['realtime_end']}"))
    return out


def refresh(store, transport, cfg: FredSourceConfig, now: datetime) -> dict:
    """Store every vintage of each configured series. Safe to rerun: the store keeps one row per key."""
    counts = {}
    for s in cfg.series:
        obs = to_observations(s.id, all_vintages(transport, s.id), cfg, s.license, now)
        counts[s.id] = store.add(obs)
    return counts
