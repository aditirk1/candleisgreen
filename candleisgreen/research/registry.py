"""Experiment registry, claim cards and evidence graph (spec Research pipeline, decision Q9).

Rules enforced here:
1. A test runs only under a pre-registered plan, and the plan is frozen by its hash.
2. Every variant tried is recorded and counts toward the trial total.
3. Varying a safeguard or an external fact is refused (parameter registry).
4. Results, including failures, are never deleted. Negative results stay visible.
5. Every change is written to the audit log.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..core.sqlite_shared import connect as sqlite_connect
from ..core.audit import AuditLog
from ..core.ids import canonical_json, make_id, sha256_hex
from ..core.parameters import ParameterRegistry, load_registry
from ..core.timeutil import iso_utc

CLAIM_STATUSES = ("DISCOVERED", "EXTRACTED", "NEEDS_DATA", "REPRODUCING", "REPRODUCED", "FAILED", "REPLICATED",
                  "OOS_PASSED", "SHADOW", "ELIGIBLE_FOR_REVIEW", "PAPER", "SUSPENDED", "RETIRED")
STUDY_TYPES = ("reproduction", "replication", "new_factor", "event_study", "forecast", "economic")
RELATIONS = ("reproduces", "replicates", "contradicts", "supports", "implements")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY, card_json TEXT NOT NULL, status TEXT NOT NULL, signal_id TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, study_type TEXT NOT NULL, plan_json TEXT NOT NULL,
    plan_hash TEXT NOT NULL, registered_at TEXT NOT NULL, status TEXT NOT NULL, passed INTEGER,
    result_json TEXT, completed_at TEXT, selection_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS variants (
    variant_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, params_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY, from_id TEXT NOT NULL, to_id TEXT NOT NULL, relation TEXT NOT NULL,
    independence TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_tiers (
    signal_id TEXT PRIMARY KEY, tier INTEGER NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS composite_runs (
    composite_run_id TEXT PRIMARY KEY, as_of TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reevaluations (
    case_id TEXT PRIMARY KEY, signal_id TEXT NOT NULL, trigger_claim_id TEXT NOT NULL, opened_at TEXT NOT NULL,
    status TEXT NOT NULL, result_json TEXT
);
CREATE TABLE IF NOT EXISTS promotions (
    proposal_id TEXT PRIMARY KEY, signal_id TEXT NOT NULL, to_tier INTEGER NOT NULL, evidence_json TEXT NOT NULL,
    proposed_at TEXT NOT NULL, status TEXT NOT NULL, decided_by TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS digests (
    digest_date TEXT PRIMARY KEY, digest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS frozen_weights (
    signal_id TEXT PRIMARY KEY, weight REAL NOT NULL, frozen_at TEXT NOT NULL
);
"""


class PlanNotRegisteredError(RuntimeError):
    pass


class GovernanceError(PermissionError):
    """Promotion above Tier 4 needs Aditi's approval. Nothing automatic can grant it."""


APPROVER = "user:aditi"
AUTO_MAX_TIER = 4


class PlanFrozenError(RuntimeError):
    pass


def _rows(cur) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class ResearchRegistry:
    def __init__(self, path: str | Path, audit: AuditLog, params: Optional[ParameterRegistry] = None,
                 shared_across_threads: bool = False):
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)
        self.audit = audit
        self.params = params or load_registry()

    def close(self) -> None:
        self.conn.close()

    def _log(self, event: str, entity: str, payload: Any, now: datetime, actor: str = "system:research") -> None:
        self.audit.append(event_type=event, entity_id=entity, payload=payload, actor=actor,
                          strategy_version="research", event_time=now, received_time=now)

    # Claims --------------------------------------------------------------------------------

    def add_claim(self, card: dict, now: datetime, signal_id: Optional[str] = None) -> str:
        cid = make_id("claim", {k: card[k] for k in sorted(card) if k not in ("ingested_at",)})
        stamp = iso_utc(now)
        cur = self.conn.execute("INSERT OR IGNORE INTO claims VALUES (?,?,?,?,?,?)",
                                (cid, canonical_json(card), "EXTRACTED", signal_id, stamp, stamp))
        if cur.rowcount:
            self._log("claim_extracted", cid, card, now)
        return cid

    def set_claim_status(self, claim_id: str, status: str, now: datetime, reason: str = "") -> None:
        if status not in CLAIM_STATUSES:
            raise ValueError(status)
        self.conn.execute("UPDATE claims SET status = ?, updated_at = ? WHERE claim_id = ?", (status, iso_utc(now), claim_id))
        self._log("claim_status", claim_id, {"status": status, "reason": reason}, now)

    def claim(self, claim_id: str) -> dict:
        rows = _rows(self.conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)))
        if not rows:
            raise KeyError(claim_id)
        r = rows[0]
        r["card"] = json.loads(r.pop("card_json"))
        return r

    def claims(self, status: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT * FROM claims", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        out = _rows(self.conn.execute(sql + " ORDER BY created_at", args))
        for r in out:
            r["card"] = json.loads(r.pop("card_json"))
        return out

    # Experiments ---------------------------------------------------------------------------

    def preregister(self, claim_id: str, study_type: str, plan: dict, now: datetime, selection_note: str = "") -> str:
        if study_type not in STUDY_TYPES:
            raise ValueError(study_type)
        for path in plan.get("varied_parameters", []):
            self.params.assert_tunable(path)
        plan_hash = sha256_hex(canonical_json(plan))
        eid = make_id("exp", {"claim": claim_id, "study": study_type, "plan": plan_hash})
        cur = self.conn.execute("INSERT OR IGNORE INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (eid, claim_id, study_type, canonical_json(plan), plan_hash, iso_utc(now), "REGISTERED",
                                 None, None, None, selection_note))
        if cur.rowcount:
            self._log("experiment_registered", eid, {"claim_id": claim_id, "study_type": study_type, "plan": plan,
                                                     "selection_note": selection_note}, now)
        return eid

    def experiment(self, experiment_id: str) -> dict:
        rows = _rows(self.conn.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)))
        if not rows:
            raise PlanNotRegisteredError(f"experiment {experiment_id} was never pre-registered")
        r = rows[0]
        r["plan"] = json.loads(r.pop("plan_json"))
        raw = r.pop("result_json")
        r["result"] = json.loads(raw) if raw else None
        r["variants"] = self.variant_count(experiment_id)
        return r

    def record_variant(self, experiment_id: str, params: dict, metrics: dict, now: datetime) -> str:
        exp = self.experiment(experiment_id)
        if exp["status"] != "REGISTERED":
            raise PlanFrozenError("the experiment is complete, a new variant needs a new pre-registration")
        for path in params:
            if "." in path and path in self.params.parameters:
                self.params.assert_tunable(path)
        vid = make_id("var", {"exp": experiment_id, "params": params, "n": self.variant_count(experiment_id)})
        self.conn.execute("INSERT INTO variants VALUES (?,?,?,?,?)",
                          (vid, experiment_id, canonical_json(params), canonical_json(metrics), iso_utc(now)))
        self._log("variant_recorded", vid, {"experiment_id": experiment_id, "params": params, "metrics": metrics}, now)
        return vid

    def variant_count(self, experiment_id: Optional[str] = None) -> int:
        if experiment_id is None:
            return self.conn.execute("SELECT count(*) FROM variants").fetchone()[0]
        return self.conn.execute("SELECT count(*) FROM variants WHERE experiment_id = ?", (experiment_id,)).fetchone()[0]

    def complete(self, experiment_id: str, plan: dict, passed: bool, result: dict, now: datetime) -> None:
        exp = self.experiment(experiment_id)
        if exp["plan_hash"] != sha256_hex(canonical_json(plan)):
            raise PlanFrozenError("the plan changed after pre-registration")
        if exp["status"] != "REGISTERED":
            raise PlanFrozenError("the experiment is already complete")
        if self.variant_count(experiment_id) == 0:
            raise PlanNotRegisteredError("no variant was recorded, so there is nothing to conclude")
        self.conn.execute("UPDATE experiments SET status = ?, passed = ?, result_json = ?, completed_at = ? "
                          "WHERE experiment_id = ?", ("PASSED" if passed else "FAILED", int(passed),
                                                       canonical_json(result), iso_utc(now), experiment_id))
        self._log("experiment_completed", experiment_id, {"passed": passed, "result": result}, now)

    def experiments(self, claim_id: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT experiment_id FROM experiments", ()
        if claim_id:
            sql, args = sql + " WHERE claim_id = ?", (claim_id,)
        return [self.experiment(r[0]) for r in self.conn.execute(sql + " ORDER BY registered_at", args).fetchall()]

    def failures(self) -> list[dict]:
        """The failure archive. Failed experiments are never removed."""
        return [self.experiment(r[0]) for r in self.conn.execute(
            "SELECT experiment_id FROM experiments WHERE status = 'FAILED' ORDER BY completed_at").fetchall()]

    # Evidence graph ------------------------------------------------------------------------

    def link(self, from_id: str, to_id: str, relation: str, independence: str, now: datetime) -> str:
        if relation not in RELATIONS:
            raise ValueError(relation)
        lid = make_id("link", {"from": from_id, "to": to_id, "rel": relation})
        cur = self.conn.execute("INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?)",
                                (lid, from_id, to_id, relation, independence, iso_utc(now)))
        if cur.rowcount:
            self._log("evidence_link", lid, {"from": from_id, "to": to_id, "relation": relation,
                                             "independence": independence}, now)
        return lid

    def links(self, node_id: Optional[str] = None) -> list[dict]:
        if node_id is None:
            return _rows(self.conn.execute("SELECT * FROM links ORDER BY created_at"))
        return _rows(self.conn.execute("SELECT * FROM links WHERE from_id = ? OR to_id = ? ORDER BY created_at",
                                       (node_id, node_id)))

    def chain(self, claim_id: str) -> dict:
        """Everything known about one claim: the card, its experiments and its links."""
        return {"claim": self.claim(claim_id), "experiments": self.experiments(claim_id), "links": self.links(claim_id)}

    # Signal tiers and Composite runs ---------------------------------------------------------

    def set_tier(self, signal_id: str, tier: int, status: str, evidence: dict, now: datetime,
                 actor: str = "system:research") -> None:
        current = self.tier(signal_id)[0]
        if tier > AUTO_MAX_TIER and tier > current and actor != APPROVER:
            raise GovernanceError(f"promotion to Tier {tier} needs Aditi's approval")
        self.conn.execute("INSERT OR REPLACE INTO signal_tiers VALUES (?,?,?,?,?)",
                          (signal_id, tier, status, canonical_json(evidence), iso_utc(now)))
        self._log("signal_tier", signal_id, {"tier": tier, "status": status, "evidence": evidence}, now)

    def tier(self, signal_id: str) -> tuple[int, str, dict]:
        rows = self.conn.execute("SELECT tier, status, evidence_json FROM signal_tiers WHERE signal_id = ?",
                                 (signal_id,)).fetchall()
        if not rows:
            return 1, "DISCOVERED", {}
        return rows[0][0], rows[0][1], json.loads(rows[0][2])

    # Governance ----------------------------------------------------------------------------

    def propose_promotion(self, signal_id: str, to_tier: int, evidence: dict, now: datetime) -> str:
        pid = make_id("promo", {"signal": signal_id, "tier": to_tier, "at": now})
        self.conn.execute("INSERT OR IGNORE INTO promotions VALUES (?,?,?,?,?,?,?,?)",
                          (pid, signal_id, to_tier, canonical_json(evidence), iso_utc(now), "PENDING", None, None))
        self._log("promotion_proposed", pid, {"signal_id": signal_id, "to_tier": to_tier, "evidence": evidence}, now)
        return pid

    def decide_promotion(self, proposal_id: str, approve: bool, actor: str, now: datetime) -> None:
        if actor != APPROVER:
            raise GovernanceError("only Aditi can decide a promotion")
        row = self.conn.execute("SELECT signal_id, to_tier, evidence_json, status FROM promotions WHERE proposal_id = ?",
                                (proposal_id,)).fetchone()
        if row is None or row[3] != "PENDING":
            raise ValueError("no pending promotion with that ID")
        status = "APPROVED" if approve else "DECLINED"
        self.conn.execute("UPDATE promotions SET status = ?, decided_by = ?, decided_at = ? WHERE proposal_id = ?",
                          (status, actor, iso_utc(now), proposal_id))
        self._log("promotion_decided", proposal_id, {"status": status}, now, actor)
        if approve:
            self.set_tier(row[0], row[1], "ELIGIBLE_FOR_REVIEW" if row[1] == 5 else "PAPER", json.loads(row[2]), now, actor)

    def promotions(self) -> list[dict]:
        return _rows(self.conn.execute("SELECT * FROM promotions ORDER BY proposed_at"))

    # Re-evaluation cases -------------------------------------------------------------------

    def open_reevaluation(self, signal_id: str, trigger_claim_id: str, now: datetime) -> str:
        cid = make_id("case", {"signal": signal_id, "trigger": trigger_claim_id})
        cur = self.conn.execute("INSERT OR IGNORE INTO reevaluations VALUES (?,?,?,?,?,?)",
                                (cid, signal_id, trigger_claim_id, iso_utc(now), "OPEN", None))
        if cur.rowcount:
            self._log("reevaluation_opened", cid, {"signal_id": signal_id, "trigger_claim_id": trigger_claim_id}, now)
        return cid

    def close_reevaluation(self, case_id: str, result: dict, now: datetime) -> None:
        self.conn.execute("UPDATE reevaluations SET status = 'CLOSED', result_json = ? WHERE case_id = ?",
                          (canonical_json(result), case_id))
        self._log("reevaluation_closed", case_id, result, now)

    def reevaluations(self, status: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT * FROM reevaluations", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        out = _rows(self.conn.execute(sql + " ORDER BY opened_at", args))
        for r in out:
            raw = r.pop("result_json")
            r["result"] = json.loads(raw) if raw else None
        return out

    # Digests -------------------------------------------------------------------------------

    def save_digest(self, digest_date: str, digest: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO digests VALUES (?,?)", (digest_date, json.dumps(digest, default=str)))

    def digests(self, limit: int = 10) -> list[dict]:
        return [json.loads(r[0]) for r in self.conn.execute(
            "SELECT digest_json FROM digests ORDER BY digest_date DESC LIMIT ?", (limit,)).fetchall()]

    def save_run(self, run_id: str, as_of: datetime, record: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO composite_runs VALUES (?,?,?)",
                          (run_id, iso_utc(as_of), json.dumps(record, default=str)))

    def latest_run(self) -> Optional[dict]:
        row = self.conn.execute("SELECT record_json FROM composite_runs ORDER BY as_of DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def frozen_weights(self) -> dict[str, float]:
        return dict(self.conn.execute("SELECT signal_id, weight FROM frozen_weights").fetchall())

    def freeze_weights(self, weights: dict[str, float], now: datetime) -> None:
        if self.frozen_weights():
            return  # frozen once, then kept as the benchmark
        for sid, w in weights.items():
            self.conn.execute("INSERT INTO frozen_weights VALUES (?,?,?)", (sid, w, iso_utc(now)))
        self._log("weights_frozen", "frozen_weights", weights, now)
