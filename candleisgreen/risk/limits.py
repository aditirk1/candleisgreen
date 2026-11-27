"""Hard-limit changes (spec Who can change what). Owned by the risk service.

Only Aditi can request a change. A change that tightens a limit applies at once. A change that
loosens one waits `risk.loosening_delay_hours` and then needs Aditi's second confirmation.
The config file holds the base values. Active changes live in the risk service's own state.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.config import HardLimits
from ..core.ids import make_id
from ..core.timeutil import ensure_utc

APPROVER = "user:aditi"
NUMERIC = ("max_position_pct_equity", "max_cluster_pct_equity", "max_order_pct_adv20", "max_spread_pct",
           "daily_loss_stop_pct_equity", "max_quote_age_seconds", "max_short_position_pct_equity",
           "max_short_exposure_pct_equity", "max_gross_exposure_pct_equity")
ZERO_ALLOWED = ("max_short_position_pct_equity", "max_short_exposure_pct_equity")  # zero turns shorting off


class LimitChangeError(PermissionError):
    pass


class LimitBook:
    def __init__(self, state_dir: Path, base: HardLimits, delay_hours: float):
        self.path = Path(state_dir) / "limit_changes.json"
        self.base = base
        self.delay = timedelta(hours=delay_hours)
        self.lock = threading.Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"active": {}, "pending": {}}
        return json.loads(self.path.read_text())

    def _save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=1))

    def effective(self) -> HardLimits:
        active = self._load()["active"]
        return self.base.model_copy(update={k: v["value"] for k, v in active.items()})

    def request(self, key: str, value: float, actor: str, now: datetime) -> dict:
        if actor != APPROVER:
            raise LimitChangeError("only Aditi can change a hard limit")
        if key not in NUMERIC or not (value > 0 or (value == 0 and key in ZERO_ALLOWED)):
            raise ValueError(f"unknown limit or invalid value: {key}")
        if key != "max_quote_age_seconds" and value > 1:
            raise ValueError("fractional limits must be at most 1")
        with self.lock:
            state = self._load()
            current = getattr(self.effective(), key)
            now = ensure_utc(now)
            if value <= current:  # every limit here is a ceiling, so a smaller value is tighter
                state["active"][key] = {"value": value, "at": now.isoformat(), "by": actor}
                state["pending"].pop(key, None)
                self._save(state)
                return {"status": "APPLIED", "key": key, "value": value}
            rid = make_id("lim", {"key": key, "value": value, "at": now})
            state["pending"][key] = {"request_id": rid, "value": value, "requested_at": now.isoformat(),
                                     "confirmable_from": (now + self.delay).isoformat(), "by": actor}
            self._save(state)
            return {"status": "WAITING", "key": key, "value": value, "confirmable_from": (now + self.delay).isoformat()}

    def confirm(self, key: str, actor: str, now: datetime) -> dict:
        if actor != APPROVER:
            raise LimitChangeError("only Aditi can confirm a loosening")
        with self.lock:
            state = self._load()
            pend = state["pending"].get(key)
            if pend is None:
                raise ValueError("no pending change for that limit")
            if ensure_utc(now) < datetime.fromisoformat(pend["confirmable_from"]):
                raise LimitChangeError(f"loosening waits until {pend['confirmable_from']}")
            state["active"][key] = {"value": pend["value"], "at": ensure_utc(now).isoformat(), "by": actor}
            del state["pending"][key]
            self._save(state)
            return {"status": "APPLIED", "key": key, "value": pend["value"]}

    def view(self) -> dict:
        state = self._load()
        return {"effective": self.effective().model_dump(), "base": self.base.model_dump(), "pending": state["pending"],
                "editable": list(NUMERIC), "delay_hours": self.delay.total_seconds() / 3600}
