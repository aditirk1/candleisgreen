"""Execution quality (spec decision Q4): slippage against the arrival mid, by time window.

Paper and simulated fills contain no market impact, so on them this measures the spread
and quote quality only. A window becomes the permanent default only after this comparison.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class WindowStats:
    window: str
    fills: int
    mean_bps: float
    stderr_bps: float

    @property
    def interval_95(self) -> tuple[float, float]:
        return self.mean_bps - 1.96 * self.stderr_bps, self.mean_bps + 1.96 * self.stderr_bps


def window_of(ts: datetime, minutes: int, tz: str = "America/New_York") -> str:
    local = ts.astimezone(ZoneInfo(tz))
    start = (local.hour * 60 + local.minute) // minutes * minutes
    end = start + minutes
    return f"{start // 60:02d}:{start % 60:02d} to {end // 60:02d}:{end % 60:02d} ET"


def by_window(fills: Iterable[dict], minutes: int = 30) -> list[WindowStats]:
    groups: dict[str, list[float]] = {}
    for f in fills:
        if f.get("slippage_bps") is None:
            continue
        ts = datetime.fromisoformat(str(f["filled_at"]).replace("Z", "+00:00"))
        groups.setdefault(window_of(ts, minutes), []).append(float(f["slippage_bps"]))
    out = []
    for name in sorted(groups):
        xs = groups[name]
        mean = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else float("nan")
        out.append(WindowStats(name, len(xs), mean, sd / math.sqrt(len(xs)) if len(xs) > 1 else float("nan")))
    return out
