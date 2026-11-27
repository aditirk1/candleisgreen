"""Run one published factor through the evidence pipeline: claim card, pre-registered
reproduction, pre-registered replication on the period after the selection cutoff, links,
and the resulting tier. Academic evidence stops at Tier 3 (spec decision Q14)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..core.config import AppConfig
from .academic import PublishedClaim, academic_record, replicate_after_cutoff, reproduce
from .registry import ResearchRegistry


def run_published_factor(claim: PublishedClaim, series: pd.Series, signal_id: str, registry: ResearchRegistry,
                         cfg: AppConfig, now: datetime, dataset: str, selection_note: str = "") -> dict:
    cid = registry.add_claim(claim.card(), now, signal_id)
    registry.set_claim_status(cid, "REPRODUCING", now)
    rep_plan = {"study": "reproduction", "dataset": dataset, "series": claim.signal,
                "period": [claim.sample_start, claim.sample_end],
                "rule": "same sign, and inside the paper's interval or at least half its size",
                "rule_parameters": ["research.reproduction.min_fraction_of_paper", "research.reproduction.interval_z"]}
    e1 = registry.preregister(cid, "reproduction", rep_plan, now, selection_note)
    r1 = reproduce(series, claim, cfg)
    registry.record_variant(e1, {"construction": "dataset long-short portfolio"}, r1, now)
    registry.complete(e1, rep_plan, r1["passed"], r1, now)
    registry.link(e1, cid, "reproduces", "same definitions and period", now)
    out = {"claim_id": cid, "reproduction": {"experiment_id": e1, **r1}}
    if not r1["passed"]:
        registry.set_claim_status(cid, "FAILED", now, "reproduction failed")
        registry.set_tier(signal_id, 1, "FAILED", {"claim_id": cid, "reproduction": e1}, now)
        out["tier"] = 1
        return out
    registry.set_claim_status(cid, "REPRODUCED", now)
    rep2_plan = {"study": "replication", "dataset": dataset, "series": claim.signal,
                 "period_after": claim.selection_cutoff_year, "independence": "period",
                 "rule": "same sign and significant at the configured level, Newey-West errors",
                 "rule_parameters": ["composite.eligibility.replication_significance", "research.monthly_hac_lag"]}
    e2 = registry.preregister(cid, "replication", rep2_plan, now)
    r2 = replicate_after_cutoff(series, claim, cfg)
    registry.record_variant(e2, {"construction": "dataset long-short portfolio"}, r2, now)
    registry.complete(e2, rep2_plan, r2["passed"], r2, now)
    registry.link(e2, cid, "replicates" if r2["passed"] else "contradicts", "period", now)
    out["replication"] = {"experiment_id": e2, **r2}
    tier = 3 if r2["passed"] else 2
    status = "REPLICATED" if r2["passed"] else "REPRODUCED"
    registry.set_claim_status(cid, status, now)
    record = academic_record(series, claim, cfg)
    registry.set_tier(signal_id, tier, status, {"claim_id": cid, "reproduction": e1, "replication": e2,
                                                "academic_record": record}, now)
    out["tier"] = tier
    out["academic_record"] = record
    return out
