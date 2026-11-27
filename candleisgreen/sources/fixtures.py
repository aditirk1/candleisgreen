"""Offline fixture collector. Turns a recorded payload into observations.

The fixture file is JSON with a `bars` list. Each bar gives one field value for one
instrument, with the times the vendor published it. No network access.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc


def _ts(text: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))


def load_fixture(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_bars(payload: dict, ingested_at: datetime) -> list[Observation]:
    """Backfill-mode collection: `first_usable_at` comes from the vendor times plus a lag."""
    lag_seconds = float(payload.get("backfill_lag_seconds", 0))
    out: list[Observation] = []
    for bar in payload["bars"]:
        event_time = _ts(bar["event_time"])
        published_at = _ts(bar["published_at"])
        vendor_available_at = _ts(bar.get("vendor_available_at", bar["published_at"]))
        usable = max(event_time, published_at, vendor_available_at)
        usable = usable.fromtimestamp(usable.timestamp() + lag_seconds, tz=usable.tzinfo)
        value = bar.get("value")
        out.append(
            Observation(
                instrument_id=bar["instrument_id"],
                vendor=payload["vendor"],
                raw_symbol=bar["raw_symbol"],
                exchange=bar["exchange"],
                field=bar["field"],
                value=value,
                event_time=event_time,
                published_at=published_at,
                vendor_available_at=vendor_available_at,
                ingested_at=ingested_at,
                first_usable_at=usable,
                timezone=payload["timezone"],
                currency=payload["currency"],
                adjustment_method=payload["adjustment_method"],
                vintage=int(bar.get("vintage", 0)),
                missing_flag=value is None,
                license=payload["license"],
                collection_mode=CollectionMode.BACKFILL,
            )
        )
    return out
