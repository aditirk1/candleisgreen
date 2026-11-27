"""Exchange calendars from the market rule table (config/markets.yaml)."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parents[1] / "config" / "markets.yaml"


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    return {e["mic"]: e for e in yaml.safe_load(PATH.read_text())["exchanges"]}


def is_trading_day(day: date, mic: str = "XNYS") -> bool:
    rule = rules()[mic]
    return day.weekday() < 5 and day.isoformat() not in {str(h) for h in rule.get("holidays", [])}


def is_early_close(day: date, mic: str = "XNYS") -> bool:
    return day.isoformat() in {str(d) for d in rules()[mic].get("early_closes", [])}


def tradable(mic: str) -> bool:
    rule = rules().get(mic)
    return bool(rule and rule["tag"] == "direct")
