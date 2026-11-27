"""Earnings scorecard (spec Phase 2). Every figure traces to an SEC filing.

"Beat" or "miss" needs a timestamped consensus estimate. No free source exists
(config/capabilities.yaml), so that column is always NOT AVAILABLE and the words never
appear. Quarterly values are the three-month periods the filings report. Fourth quarters
reported only inside an annual total are not derived, because share counts change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from .core.capabilities import CapabilityNotAvailableError, load_capabilities
from .core.timeutil import ensure_utc
from .data.pit_store import PointInTimeStore

EPS = "us-gaap:EarningsPerShareDiluted:USD/shares"
REVENUE = ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax:USD", "us-gaap:Revenues:USD")
QUARTER_DAYS = (80, 100)


@dataclass(frozen=True)
class ScorecardRow:
    period_end: date
    eps_diluted: float
    eps_yoy_change: Optional[float]
    revenue: Optional[float]
    revenue_yoy_pct: Optional[float]
    filed_at: datetime
    source: str  # accession number, form and URL of the filing
    observation_id: str
    vs_consensus: Optional[str]
    vs_consensus_label: str


def consensus_label() -> str:
    try:
        load_capabilities().require("analyst_consensus_estimates")
        return "AVAILABLE"
    except CapabilityNotAvailableError as exc:
        return str(exc).split(": ", 1)[1]


def _quarterly(store: PointInTimeStore, instrument_id: str, prefix: str, when: datetime) -> dict[date, tuple]:
    """Latest usable vintage per three-month period whose field starts with `prefix`."""
    rows = store.connection.execute(
        "SELECT DISTINCT field FROM observations WHERE instrument_id = ? AND vendor = 'sec' AND field LIKE ?",
        [instrument_id, prefix + ":%"]).fetchall()
    out: dict[date, tuple] = {}
    for (field,) in rows:
        start = field.rsplit(":", 1)[1]
        if start == "instant":
            continue
        for obs in store.as_of(when).series(instrument_id, field):
            length = (obs.event_time.date() - date.fromisoformat(start)).days
            if QUARTER_DAYS[0] <= length <= QUARTER_DAYS[1]:
                out[obs.event_time.date()] = (obs.value, obs)
    return out


def _year_before(series: dict[date, tuple], end: date) -> Optional[float]:
    for d, (v, _) in series.items():
        if abs((end - d).days - 365) <= 10:
            return v
    return None


def scorecard(store: PointInTimeStore, instrument_id: str, as_of: datetime) -> list[ScorecardRow]:
    as_of = ensure_utc(as_of)
    eps = _quarterly(store, instrument_id, EPS, as_of)
    rev: dict[date, tuple] = {}
    for prefix in REVENUE:
        for k, v in _quarterly(store, instrument_id, prefix, as_of).items():
            rev.setdefault(k, v)
    label = consensus_label()
    rows = []
    for end in sorted(eps, reverse=True):
        value, obs = eps[end]
        prior = _year_before(eps, end)
        r = rev.get(end, (None, None))[0]
        r_prior = _year_before(rev, end)
        rows.append(ScorecardRow(
            period_end=end, eps_diluted=value, eps_yoy_change=None if prior is None else value - prior,
            revenue=r, revenue_yoy_pct=None if r is None or not r_prior else (r - r_prior) / r_prior,
            filed_at=obs.first_usable_at, source=obs.source_ref or "", observation_id=obs.observation_id,
            vs_consensus=None, vs_consensus_label=label))
    return rows
