"""Pre-open check at 09:00 ET (spec C.1). It may cancel buy orders and can never add any.

A buy is cancelled when, since the decision time, its name was halted, had a corporate action
take effect, or filed an 8-K (earnings releases are 8-Ks). Sells are left alone, because they
reduce risk.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Iterable

from .core.timeutil import ensure_utc
from .data.instruments import InstrumentMaster
from .journal import Journal

ACTOR = "system:preopen"


def run(session_date: date, now: datetime, decision_time: datetime, journal: Journal, master: InstrumentMaster,
        halted: Iterable[str], filings_since: Callable[[str, datetime], list[str]]) -> list[dict]:
    halted = set(halted)
    cancelled = []
    for p in journal.proposals(session_date):
        if p.side != "buy" or p.status not in ("proposed", "approved"):
            continue
        reasons = []
        if p.symbol in halted:
            reasons.append("trading halt since the decision")
        acts = [a for a in master.actions(p.instrument_id)
                if a["effective_date"] and decision_time.date() < a["effective_date"] <= session_date]
        if acts:
            reasons.append(f"corporate action effective {acts[0]['effective_date']}: {acts[0]['action_type']}")
        forms = [f for f in filings_since(p.instrument_id, decision_time) if f.startswith("8-K")]
        if forms:
            reasons.append("8-K filed since the decision")
        if reasons:
            journal.set_status(p.proposal_id, "cancelled", ACTOR, ensure_utc(now), "pre-open check: " + ", ".join(reasons))
            cancelled.append({"proposal_id": p.proposal_id, "symbol": p.symbol, "reasons": reasons})
    return cancelled
