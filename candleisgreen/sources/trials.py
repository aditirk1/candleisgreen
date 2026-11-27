"""Clinical trials for the research-only biotech universe, from the ClinicalTrials.gov API v2.

The API serves only the most recent version of each study (its OpenAPI description says so), so
history cannot be rebuilt point in time. The system records forward: each run stores a snapshot
of every trial whose content changed, usable from the moment it was collected. A change between
two snapshots, such as a new overall status or a moved primary completion date, is a trial event.

Matching a trial to a company uses an exact match of the trial's lead sponsor to a registered
entity name (from the SEC submissions file), after removing case, punctuation and legal suffixes.
Anything less certain is not linked. Biotech names are research only and can never receive orders.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..core.config import TrialsSourceConfig
from ..core.timeutil import ensure_utc, from_micros, to_micros
from ..data.instruments import InstrumentMaster

FIELDS = ("NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,PrimaryCompletionDate,PrimaryCompletionDateType,"
          "LastUpdatePostDate,EnrollmentCount,PrimaryOutcomeMeasure,Condition")
_DDL = """
CREATE TABLE IF NOT EXISTS trial_snapshots (
    nct_id VARCHAR NOT NULL, instrument_id VARCHAR NOT NULL, observed_at BIGINT NOT NULL, content_hash VARCHAR NOT NULL,
    title VARCHAR, overall_status VARCHAR, phases VARCHAR, lead_sponsor VARCHAR, primary_completion VARCHAR,
    primary_completion_type VARCHAR, last_update_posted VARCHAR, enrollment INTEGER, primary_outcomes VARCHAR,
    conditions VARCHAR, PRIMARY KEY (nct_id, observed_at)
);
"""
_SUFFIX = re.compile(r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|lp|ag|sa|nv|se|holdings?)\b")
TRACKED = ("overall_status", "phases", "primary_completion", "primary_completion_type", "enrollment", "primary_outcomes")


def normalize(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", s)).strip()


class HttpTrialsTransport:
    def __init__(self, cfg: TrialsSourceConfig):
        self.base = cfg.base_url.rstrip("/")

    def get(self, path: str, params: dict) -> Any:
        url = f"{self.base}/{path}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))


class FixtureTrialsTransport:
    """Responses on disk, one file per normalized lead sponsor, paged by `pageSize`."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def get(self, path: str, params: dict) -> Any:
        f = self.dir / f"{normalize(params['query.lead']).replace(' ', '_')}.json"
        studies = json.loads(f.read_text())["studies"] if f.exists() else []
        start = int(params.get("pageToken") or 0)
        size = int(params["pageSize"])
        page = studies[start:start + size]
        out = {"studies": page}
        if start + size < len(studies):
            out["nextPageToken"] = str(start + size)
        return out


def fetch(transport, sponsor: str, page_size: int) -> list[dict]:
    """Every study whose lead sponsor search matches, then kept only on an exact normalized match."""
    studies, token = [], None
    while True:
        params = {"query.lead": sponsor, "fields": FIELDS, "pageSize": page_size, "format": "json"}
        if token:
            params["pageToken"] = token
        data = transport.get("studies", params)
        studies += data.get("studies", [])
        token = data.get("nextPageToken")
        if not token:
            break
    want = normalize(sponsor)
    return [s for s in studies if normalize(_lead(s)) == want]


def _lead(study: dict) -> str:
    return study.get("protocolSection", {}).get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")


def flatten(study: dict) -> dict:
    p = study.get("protocolSection", {})
    ident, status = p.get("identificationModule", {}), p.get("statusModule", {})
    design, outcomes = p.get("designModule", {}), p.get("outcomesModule", {})
    pc = status.get("primaryCompletionDateStruct", {})
    return {
        "nct_id": ident.get("nctId"), "title": ident.get("briefTitle"), "overall_status": status.get("overallStatus"),
        "phases": ",".join(design.get("phases", []) or []) or None, "lead_sponsor": _lead(study),
        "primary_completion": pc.get("date"), "primary_completion_type": pc.get("type"),
        "last_update_posted": status.get("lastUpdatePostDateStruct", {}).get("date"),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "primary_outcomes": " | ".join(o.get("measure", "") for o in outcomes.get("primaryOutcomes", []) or []) or None,
        "conditions": ", ".join(p.get("conditionsModule", {}).get("conditions", []) or []) or None,
    }


def _hash(row: dict) -> str:
    return hashlib.sha256(json.dumps({k: row.get(k) for k in sorted(row) if k != "nct_id"}, sort_keys=True).encode()).hexdigest()[:24]


def biotech_names(master: InstrumentMaster, sic_codes: tuple[int, ...], when: datetime) -> dict[str, list[str]]:
    """Instrument to entity names, for names whose latest SIC code known at `when` is a biotech code."""
    out: dict[str, list[str]] = {}
    for iid, name in master.entity_names():
        cls = [c for c in master.classifications(iid) if c["classified_at"] <= to_micros(ensure_utc(when))]
        if cls and cls[-1]["sic_code"] in sic_codes:
            out.setdefault(iid, []).append(name)
    return out


def record(conn, transport, master: InstrumentMaster, sic_codes: tuple[int, ...], cfg: TrialsSourceConfig,
           now: datetime) -> dict:
    """One forward snapshot. Stores only trials whose content changed. Safe to rerun."""
    for stmt in _DDL.strip().split(";"):
        if stmt.strip():
            conn.execute(stmt).fetchall()
    now = ensure_utc(now)
    names = biotech_names(master, sic_codes, now)
    added, seen = 0, 0
    for iid, entity_names in names.items():
        for name in entity_names:
            for study in fetch(transport, name, cfg.page_size):
                row = flatten(study)
                if not row["nct_id"]:
                    continue
                seen += 1
                h = _hash(row)
                last = conn.execute("SELECT content_hash FROM trial_snapshots WHERE nct_id = ? "
                                    "ORDER BY observed_at DESC LIMIT 1", [row["nct_id"]]).fetchall()
                if last and last[0][0] == h:
                    continue
                conn.execute("INSERT OR REPLACE INTO trial_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             [row["nct_id"], iid, to_micros(now), h, row["title"], row["overall_status"], row["phases"],
                              row["lead_sponsor"], row["primary_completion"], row["primary_completion_type"],
                              row["last_update_posted"], row["enrollment"], row["primary_outcomes"], row["conditions"]]).fetchall()
                added += 1
    return {"companies": len(names), "trials_seen": seen, "snapshots_added": added}


def _rows(conn, sql: str, args: list) -> list[dict]:
    cur = conn.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def as_of(conn, when: datetime, instrument_id: Optional[str] = None) -> list[dict]:
    """Each trial as it was known at `when`: its latest snapshot collected before then."""
    try:
        rows = _rows(conn, "SELECT * FROM trial_snapshots WHERE observed_at < ?" +
                     (" AND instrument_id = ?" if instrument_id else "") + " ORDER BY observed_at",
                     [to_micros(ensure_utc(when))] + ([instrument_id] if instrument_id else []))
    except Exception:
        return []
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r["nct_id"]] = r
    for r in latest.values():
        r["observed_at"] = from_micros(r["observed_at"]).isoformat()
    return sorted(latest.values(), key=lambda r: r["nct_id"])


def events(conn, since: datetime, until: datetime) -> list[dict]:
    """Changes in tracked fields between consecutive snapshots of the same trial, first seen in (since, until]."""
    try:
        rows = _rows(conn, "SELECT * FROM trial_snapshots WHERE observed_at <= ? ORDER BY nct_id, observed_at",
                     [to_micros(ensure_utc(until))])
    except Exception:
        return []
    out, prev = [], {}
    for r in rows:
        p = prev.get(r["nct_id"])
        if p and r["observed_at"] > to_micros(ensure_utc(since)):
            for f in TRACKED:
                if p[f] != r[f]:
                    out.append({"nct_id": r["nct_id"], "instrument_id": r["instrument_id"], "field": f, "before": p[f],
                                "after": r[f], "observed_at": from_micros(r["observed_at"]).isoformat()})
        prev[r["nct_id"]] = r
    return out
