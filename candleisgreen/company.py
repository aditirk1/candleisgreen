"""Company intelligence (Priority 6). Every number carries its source, its measurement period and how old
it is. A figure without a source is NOT AVAILABLE with the reason, never estimated.

Sources used: SEC submissions (name, SIC code and description, state, fiscal year end), SEC XBRL company
facts (revenue, earnings, assets, equity), recorded daily prices and volume, the trend model, the news store
and recorded clinical trials. A business description beyond the SEC industry code, the revenue model and the
10-K risk factors are not parsed, and say so.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

from .core.timeutil import ensure_utc
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore

QUARTER = (80, 100)
YEAR = (350, 380)
CONCEPTS = {
    "revenue": ("Revenue", ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax:USD", "us-gaap:Revenues:USD"), "USD"),
    "net_income": ("Net income", ("us-gaap:NetIncomeLoss:USD",), "USD"),
    "operating_income": ("Operating income", ("us-gaap:OperatingIncomeLoss:USD",), "USD"),
    "eps_diluted": ("Diluted earnings per share", ("us-gaap:EarningsPerShareDiluted:USD/shares",), "USD per share"),
    "assets": ("Total assets", ("us-gaap:Assets:USD",), "USD"),
    "equity": ("Shareholders' equity", ("us-gaap:StockholdersEquity:USD",), "USD"),
}


def _na(label: str, reason: str, unit: str = "") -> dict:
    return {"label": label, "status": "NOT AVAILABLE", "reason": reason, "value": None, "unit": unit}


def _metric(label: str, value: float, unit: str, period: str, source: str, as_of: datetime, now: datetime, **extra) -> dict:
    return {"label": label, "status": "OK", "value": value, "unit": unit, "period": period, "source": source,
            "as_of": as_of.isoformat(), "age_days": (ensure_utc(now) - ensure_utc(as_of)).days, **extra}


def _facts(store: PointInTimeStore, iid: str, prefixes: tuple[str, ...], kind: str, when: datetime) -> list[tuple]:
    """(period_start, period_end, observation) for duration facts of the given kind, or instants. Latest vintage known by `when`."""
    out: dict[date, tuple] = {}
    for prefix in prefixes:
        rows = store.connection.execute(
            "SELECT DISTINCT field FROM observations WHERE instrument_id = ? AND vendor = 'sec' AND field LIKE ?",
            [iid, prefix + ":%"]).fetchall()
        for (field,) in rows:
            start = field.rsplit(":", 1)[1]
            for o in store.as_of(when).series(iid, field):
                end = o.event_time.date()
                if kind == "instant":
                    if start != "instant":
                        continue
                    out.setdefault(end, (None, end, o))
                    continue
                if start == "instant":
                    continue
                length = (end - date.fromisoformat(start)).days
                lo, hi = QUARTER if kind == "quarter" else YEAR
                if lo <= length <= hi:
                    out.setdefault(end, (date.fromisoformat(start), end, o))
    return [out[k] for k in sorted(out)]


def _source(o) -> str:
    return o.source_ref or f"{o.vendor} {o.field}"


def fundamentals(store: PointInTimeStore, iid: str, now: datetime) -> dict:
    out = {}
    for key, (label, prefixes, unit) in CONCEPTS.items():
        kind = "instant" if key in ("assets", "equity") else "quarter"
        rows = _facts(store, iid, prefixes, kind, now)
        if not rows:
            out[key] = _na(label, "No SEC filing value recorded for this company", unit)
            continue
        start, end, o = rows[-1]
        period = f"as of {end}" if kind == "instant" else f"quarter {start} to {end}"
        out[key] = _metric(label, o.value, unit, period, _source(o), o.first_usable_at, now, period_end=end.isoformat())
        if kind == "quarter":
            annual = _facts(store, iid, prefixes, "year", now)
            if annual:
                s, e, a = annual[-1]
                out[key + "_annual"] = _metric(f"{label}, fiscal year", a.value, unit, f"year {s} to {e}", _source(a),
                                               a.first_usable_at, now, period_end=e.isoformat())
    eps = _facts(store, iid, CONCEPTS["eps_diluted"][1], "quarter", now)
    if len(eps) >= 4 and (eps[-1][1] - eps[-4][0]).days <= 380:
        last4 = eps[-4:]
        out["eps_ttm"] = _metric("Diluted earnings per share, last four quarters", sum(o.value for _, _, o in last4), "USD per share",
                                 f"{last4[0][0]} to {last4[-1][1]}", "; ".join(_source(o).split(" ")[0] for _, _, o in last4),
                                 max(o.first_usable_at for _, _, o in last4), now)
    else:
        out["eps_ttm"] = _na("Diluted earnings per share, last four quarters", "Fewer than four consecutive quarters recorded", "USD per share")
    return out


def valuation(fund: dict, price: Optional[dict], now: datetime) -> dict:
    """Only ratios whose every input has a source. Shares outstanding are not collected, so price to book and price to sales are not available."""
    out = {}
    ttm = fund.get("eps_ttm", {})
    if price is None:
        out["pe"] = _na("Price to earnings", "No recorded price")
    elif ttm.get("status") != "OK":
        out["pe"] = _na("Price to earnings", ttm.get("reason", "No earnings"))
    elif ttm["value"] <= 0:
        out["pe"] = _na("Price to earnings", "Earnings over the last four quarters are zero or negative")
    else:
        out["pe"] = _metric("Price to earnings", price["value"] / ttm["value"], "times", f"price {price['date']}, earnings {ttm['period']}",
                            f"price {price['source']}, earnings {ttm['source']}", min(datetime.fromisoformat(ttm["as_of"]), price["as_of_dt"]), now)
    for key, label in (("pb", "Price to book"), ("ps", "Price to sales")):
        out[key] = _na(label, "Shares outstanding are not collected yet, so this ratio would need an unsourced input")
    return out


def risks(adj: list[float], volumes: list[float], closes: list[float], tag: str, synthetic: bool, cfg) -> list[dict]:
    """Risks the system can measure. The 10-K risk factors (Item 1A) are not parsed."""
    out = []
    rets = [b / a - 1 for a, b in zip(adj[-64:-1], adj[-63:]) if a]
    if len(rets) > 2:
        m = sum(rets) / len(rets)
        vol = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1) * 252)
        worst = min(rets)
        out.append({"risk": "Price swings", "detail": f"{vol:.0%} a year over the last 63 sessions, worst day {worst:.1%}", "source": "recorded daily closes"})
    n = cfg.universe.dollar_volume_window_days
    dv = sorted(v * c for v, c in zip(volumes[-n:], closes[-n:]))
    if dv:
        med = dv[len(dv) // 2]
        low = med < cfg.universe.min_median_dollar_volume_20d
        out.append({"risk": "Trading volume", "detail": f"median {med / 1e6:.1f} million USD a day over {len(dv)} sessions"
                    + (", below the universe minimum" if low else ""), "source": "recorded daily volume and closes"})
    if tag == "research_only":
        out.append({"risk": "Cannot be traded", "detail": "Research only. Orders are blocked", "source": "instrument tag"})
    if synthetic:
        out.append({"risk": "Demo data", "detail": "Every price for this company is invented", "source": "data vendor label"})
    out.append({"risk": "Company-reported risk factors", "detail": "NOT AVAILABLE. The 10-K risk factors section is not parsed yet", "source": "none"})
    return out
