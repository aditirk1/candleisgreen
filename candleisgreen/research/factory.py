"""Daily Hypothesis Factory (spec Research pipeline, Phase 5).

collect, cluster duplicates, check novelty against the signal library, check data, pre-register,
run only built-in studies (code from papers is never executed), record, and publish a digest.
A new claim that contradicts an active signal opens a re-evaluation case. Nothing here sets a
weight, places an order or touches a risk limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from ..core.config import AppConfig
from ..sources.rss import similarity
from .registry import ResearchRegistry

# Free substitutes the factory may suggest for missing data. Paid sources are never suggested.
FREE_SUBSTITUTES = {
    "analyst estimates": "none free, earnings scorecard without consensus",
    "options data": "none free",
    "intraday quotes": "daily consolidated bars from Alpaca",
    "crsp": "Open Source Asset Pricing portfolio returns for portfolio-level tests",
    "compustat": "SEC EDGAR XBRL facts from 2009",
}

Runner = Callable[[str, dict], Optional[dict]]


@dataclass(frozen=True)
class Library:
    """Active signals: id to definition, and the claim that supports each."""
    definitions: dict[str, str]
    claims: dict[str, str]


def _similar_claim(registry: ResearchRegistry, card: dict, threshold: float) -> Optional[str]:
    for c in registry.claims():
        other = c["card"]
        if card.get("doi") and card.get("doi") == other.get("doi"):
            return c["claim_id"]
        if similarity(card.get("title", ""), other.get("title", "")) >= threshold:
            return c["claim_id"]
    return None


def _novelty(card: dict, library: Library, threshold: float) -> Optional[str]:
    text = f"{card.get('title', '')} {card.get('definition', '')}"
    best, best_sim = None, 0.0
    for sid, definition in library.definitions.items():
        sim = similarity(text, definition)
        if sim > best_sim:
            best, best_sim = sid, sim
    return best if best_sim >= threshold else None


def run_daily(cards: list[dict], registry: ResearchRegistry, library: Library, available: set[str], cfg: AppConfig,
              now: datetime, runners: Optional[dict[str, Runner]] = None) -> dict:
    crit = cfg.research.criteria
    runners = runners or {}
    digest = {"date": now.date().isoformat(), "new_hypotheses": [], "duplicates": [], "linked_to_signals": [],
              "needs_data": [], "results": [], "contradictions": [], "reevaluations_opened": [], "queued": []}
    for card in cards:
        dup = _similar_claim(registry, card, crit.novelty_similarity)
        if dup:
            digest["duplicates"].append({"title": card.get("title"), "same_as": dup})
            continue
        cid = registry.add_claim(card, now)
        related = card.get("about_signal") or _novelty(card, library, crit.novelty_similarity)
        if related and related in library.definitions:
            stance = card.get("stance", "supports")
            target = library.claims.get(related, related)
            registry.link(cid, target, "contradicts" if stance == "contradicts" else "supports", "different authors", now)
            digest["linked_to_signals"].append({"claim_id": cid, "signal_id": related, "stance": stance})
            if stance == "contradicts" and registry.tier(related)[0] >= 2:
                case = registry.open_reevaluation(related, cid, now)
                digest["contradictions"].append({"claim_id": cid, "signal_id": related})
                digest["reevaluations_opened"].append(case)
            continue
        missing = [d for d in card.get("data_required", []) if d not in available]
        if missing:
            registry.set_claim_status(cid, "NEEDS_DATA", now, ", ".join(missing))
            digest["needs_data"].append({"claim_id": cid, "missing": missing,
                                         "free_substitute": {m: FREE_SUBSTITUTES.get(m.lower(), "none known") for m in missing}})
            continue
        study = card.get("study_type", "reproduction")
        plan = {"study": study, "rule": RULES.get(study, "pre-registered by hand"), "data": card.get("data_required", [])}
        eid = registry.preregister(cid, study, plan, now)
        digest["new_hypotheses"].append({"claim_id": cid, "experiment_id": eid, "study": study})
        runner = runners.get(card.get("runner", ""))
        if runner is None:
            digest["queued"].append(eid)
            continue
        result = runner(cid, card)
        if result is None:
            digest["queued"].append(eid)
            continue
        registry.record_variant(eid, {"runner": card["runner"]}, result, now)
        registry.complete(eid, plan, bool(result["passed"]), result, now)
        registry.set_claim_status(cid, "REPRODUCED" if result["passed"] else "FAILED", now)
        digest["results"].append({"experiment_id": eid, "passed": bool(result["passed"])})
    registry.save_digest(digest["date"], digest)
    return digest


RULES = {
    "reproduction": "same sign, and inside the paper's interval or at least half its size",
    "replication": "same sign and significant at the configured level on new data, independence recorded",
    "new_factor": "t above 3.0, and FDR under 5% across the trial registry (Benjamini-Yekutieli), and an untouched holdout pass",
    "event_study": "abnormal return interval excludes zero with clustered errors, FDR across events",
    "forecast": "beats its baseline at one-sided 5% (Clark-West if nested, else Diebold-Mariano) and holds in 2 of 3 subperiods",
    "economic": "lower bound of the block-bootstrap 90% interval of net excess return above zero at double modeled costs",
}


def reevaluate(registry: ResearchRegistry, case_id: str, rerun: Callable[[str], dict], now: datetime) -> dict:
    """Re-run the signal's tests on current data and update its tier. Never edits a live weight:
    the Composite reads the new tier at its next run."""
    case = next(c for c in registry.reevaluations() if c["case_id"] == case_id)
    sid = case["signal_id"]
    tier, status, evidence = registry.tier(sid)
    result = rerun(sid)
    if not result["passed"] and tier > 1:
        registry.set_tier(sid, tier - 1, "SUSPENDED", {**evidence, "reevaluation": case_id}, now)
    registry.close_reevaluation(case_id, {**result, "tier_before": tier, "tier_after": registry.tier(sid)[0]}, now)
    return result
