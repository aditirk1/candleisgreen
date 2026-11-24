"""SEC EDGAR: filing timestamps, XBRL facts and SIC classifications (spec Phase 2, decision Q10).

Every fact becomes an observation whose `first_usable_at` is the filing's acceptance time,
and whose `source_ref` names the filing, so every financial figure traces to an SEC
filing. A value first reported later or restated becomes a new vintage, never an edit.
The User-Agent with contact details comes from an environment variable only.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from ..core.config import AppConfig, SecSourceConfig
from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc, local_to_utc
from ..data.instruments import InstrumentMaster

VENDOR = "sec"
LICENSE = "us_government_public"
MARKET_TZ = "America/New_York"
FF12_PATH = Path(__file__).resolve().parents[2] / "config" / "ff12_sic.yaml"


class MissingUserAgentError(RuntimeError):
    pass


class HttpSecTransport:
    """Throttled to the fair-access limit. Reads the User-Agent from the environment."""

    def __init__(self, cfg: SecSourceConfig):
        self.ua = os.environ.get(cfg.user_agent_env)
        if not self.ua:
            raise MissingUserAgentError(f"set {cfg.user_agent_env} to a name and contact email, as SEC requires")
        self.min_gap = 1.0 / cfg.max_requests_per_second
        self.last = 0.0
        self.lock = threading.Lock()

    def get_json(self, url: str) -> Any:
        with self.lock:
            wait = self.min_gap - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class FixtureSecTransport:
    """Recorded SEC responses on disk, keyed by URL path. No network."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def get_json(self, url: str) -> Any:
        name = url.split("://", 1)[1].replace("/", "__")
        return json.loads((self.dir / name).read_text())


def cik10(cik: str | int) -> str:
    return str(int(cik)).zfill(10)


class SecClient:
    def __init__(self, transport: Any, cfg: SecSourceConfig):
        self.t = transport
        self.cfg = cfg

    def submissions(self, cik: str) -> dict:
        return self.t.get_json(f"{self.cfg.data_base_url}/submissions/CIK{cik10(cik)}.json")

    def companyfacts(self, cik: str) -> dict:
        return self.t.get_json(f"{self.cfg.data_base_url}/api/xbrl/companyfacts/CIK{cik10(cik)}.json")

    def tickers(self) -> dict[str, str]:
        raw = self.t.get_json(self.cfg.tickers_url)
        return {row["ticker"]: cik10(row["cik_str"]) for row in raw.values()}


def filing_index(submissions: dict) -> dict[str, dict]:
    """Accession number to form, filing date and acceptance time, from the recent filings list."""
    r = submissions["filings"]["recent"]
    out = {}
    for i, accn in enumerate(r["accessionNumber"]):
        out[accn] = {"form": r["form"][i], "filing_date": r["filingDate"][i],
                     "acceptance": r["acceptanceDateTime"][i] or None, "report_date": r["reportDate"][i] or None,
                     "primary_document": r["primaryDocument"][i] if "primaryDocument" in r else None}
    return out


def filing_url(cfg: SecSourceConfig, cik: str, accn: str) -> str:
    return f"{cfg.archives_base_url}/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"


def published_time(row: dict, filing: Optional[dict], cfg: SecSourceConfig) -> datetime:
    """Acceptance time in UTC when known. Otherwise the 17:30 ET cutoff on the filing date."""
    if filing and filing.get("acceptance"):
        return ensure_utc(datetime.fromisoformat(filing["acceptance"].replace("Z", "+00:00")))
    return local_to_utc(date.fromisoformat(row["filed"]), cfg.filed_date_fallback_time_local, MARKET_TZ)


def facts_to_observations(cik: str, instrument_id: str, facts: dict, filings: dict[str, dict], now: datetime,
                          cfg: AppConfig) -> list[Observation]:
    sec = cfg.sources.sec
    out: list[Observation] = []
    for qualified in sec.concepts:
        taxonomy, concept = qualified.split(":", 1)
        node = facts.get("facts", {}).get(taxonomy, {}).get(concept)
        if not node:
            continue
        for unit, rows in node["units"].items():
            groups: dict[tuple, list[dict]] = {}
            for row in rows:
                groups.setdefault((row.get("start"), row["end"]), []).append(row)
            for (start, end), reported in groups.items():
                field = f"{taxonomy}:{concept}:{unit}:{start or 'instant'}"
                event = local_to_utc(date.fromisoformat(end), "00:00", MARKET_TZ)
                ordered = sorted(reported, key=lambda r: published_time(r, filings.get(r["accn"]), sec))
                vintage, last_val = -1, None
                for row in ordered:
                    if row["val"] == last_val:
                        continue  # a repeat of a known value is not new information
                    vintage += 1
                    last_val = row["val"]
                    pub = max(published_time(row, filings.get(row["accn"]), sec), event)
                    out.append(Observation(
                        instrument_id=instrument_id, vendor=VENDOR, raw_symbol=f"CIK{cik10(cik)}", exchange="",
                        field=field, value=float(row["val"]), event_time=event, published_at=pub,
                        vendor_available_at=pub, ingested_at=ensure_utc(now), first_usable_at=pub, timezone=MARKET_TZ,
                        currency="USD" if unit.startswith("USD") else unit, adjustment_method="as_reported",
                        vintage=vintage, missing_flag=False, license=LICENSE, collection_mode=CollectionMode.BACKFILL,
                        source_ref=f"{row['accn']} {row.get('form', '')} {filing_url(sec, cik, row['accn'])}"))
    return out


def load_ff12(path: Path = FF12_PATH) -> tuple[str, list[dict]]:
    raw = yaml.safe_load(path.read_text())
    return raw["mapping_version"], raw["industries"]


def ff12_for(sic: Any, industries: list[dict]) -> tuple[str, str]:
    """Returns (industry code, status). Missing or invalid SIC is UNKNOWN."""
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return "UNKNOWN", "unknown"
    if code <= 0 or code > 9999:
        return "UNKNOWN", "unknown"
    hits = [g["code"] for g in industries if any(a <= code <= b for a, b in g["ranges"])]
    if len(hits) > 1:
        return "UNKNOWN", "ambiguous"
    return (hits[0] if hits else "Other"), "known"


def ingest_issuer(client: SecClient, cik: str, ticker: Optional[str], store, master: InstrumentMaster, now: datetime,
                  cfg: AppConfig) -> dict:
    subs = client.submissions(cik)
    facts = client.companyfacts(cik)
    filings = filing_index(subs)
    iid = master.map_issuer(cik10(cik), ticker or (subs.get("tickers") or [None])[0], now)
    added = store.add(facts_to_observations(cik, iid, facts, filings, now, cfg))
    master.add_entity_name(iid, subs.get("name") or "", "sec_submissions", now)
    version, industries = load_ff12()
    industry, status = ff12_for(subs.get("sic"), industries)
    latest = next(iter(filings), None)
    master.add_classification(iid, cik10(cik), int(subs["sic"]) if str(subs.get("sic", "")).isdigit() else None,
                              industry, status, now, latest, version)
    return {"instrument_id": iid, "observations_added": added, "industry": industry, "filings": len(filings)}
