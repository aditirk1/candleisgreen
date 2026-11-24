"""Reasoning and "Why not?" for one ticker (spec Teaching and Interface).

Built only from recorded facts: the journal, the audit log, the latest Composite run,
the news store and the point-in-time store. Nothing is inferred or invented.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .core.audit import AuditLog
from .journal import Journal
from .research.registry import ResearchRegistry
from .sources.rss import NewsStore


def _audit_payloads(audit: AuditLog, event_type: str) -> list[dict]:
    out = []
    for r in audit.records():
        if r["event_type"] == event_type:
            p = json.loads(r["payload_json"])
            p["_entity_id"] = r["entity_id"]
            p["_time"] = r["event_time_utc"]
            out.append(p)
    return out


def explain(symbol: str, now: datetime, journal: Journal, audit: AuditLog, research: ResearchRegistry,
            news: NewsStore, instrument_for, freshness) -> dict:
    iid = instrument_for(symbol)
    if iid is None:
        return {"symbol": symbol, "status": "NOT AVAILABLE", "reason": "Unknown ticker"}
    props = [p for p in journal.proposals() if p.instrument_id == iid]
    proposal = props[-1] if props else None
    forecasts = [f for f in _audit_payloads(audit, "forecast_issued") if f.get("asset_id") == iid]
    forecast = forecasts[-1] if forecasts else None
    risk = None
    if proposal and proposal.client_order_id:
        risks = [r for r in _audit_payloads(audit, "risk_decision") if r.get("client_order_id") == proposal.client_order_id]
        risk = risks[-1] if risks else None
    run = research.latest_run() or {}
    contrib = (run.get("contributions") or {}).get(symbol, {})
    agreeing = sorted([(k, v) for k, v in contrib.items() if v > 0], key=lambda kv: -kv[1])
    opposing = sorted([(k, v) for k, v in contrib.items() if v < 0], key=lambda kv: kv[1])
    exclusions = [{"signal_id": s["signal_id"], "reasons": s["reasons"]} for s in run.get("signals", []) if not s.get("eligible")]
    uncertainty = [{"signal_id": s["signal_id"], "mu_hat": s["mu_hat"], "prob_positive": s["prob_positive"]}
                   for s in run.get("signals", [])]
    why_not = None
    if proposal is None:
        if forecast is None:
            why_not = "No forecast: the name was not in the tradable universe or had too little history at the last decision"
        elif (forecast.get("signal_strength") or 0) <= 0:
            why_not = f"The trend signal was not positive ({forecast.get('signal_strength'):.2f}), and the book is long only"
        else:
            why_not = "The position was already at its target, so no trade was needed"
    elif proposal.status in ("blocked", "rejected", "expired", "broker_rejected"):
        why_not = f"Proposal {proposal.status}: {proposal.reason.splitlines()[0] if proposal.reason else 'no reason recorded'}"
    return {
        "symbol": symbol, "instrument_id": iid, "status": "OK",
        "proposal": None if proposal is None else {"proposal_id": proposal.proposal_id, "side": proposal.side,
                                                   "quantity": proposal.quantity, "status": proposal.status,
                                                   "reason": proposal.reason, "session_date": proposal.session_date},
        "forecast": None if forecast is None else {k: forecast.get(k) for k in (
            "model_id", "model_version", "signal_strength", "as_of", "calibration_status", "data_snapshot_id",
            "record_type", "data_licenses")},
        "risk": None if risk is None else {"verdict": risk.get("verdict"), "reasons": risk.get("reasons"),
                                           "checks_run": risk.get("checks_run"), "decided_at": risk.get("decided_at")},
        "composite": {"run_id": run.get("composite_run_id"), "record_type": run.get("record_type"),
                      "agreeing": agreeing, "opposing": opposing, "exclusions": exclusions, "uncertainty": uncertainty},
        "freshness": freshness(iid),
        "news": [{"title": n.title, "feed": n.feed, "usable_from": n.first_usable_at.isoformat(), "link": n.link}
                 for n in news.as_of(now, ticker=symbol, limit=10)],
        "why_not": why_not,
    }
