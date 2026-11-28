"""Insider transactions (SEC Form 4), institutional holdings (SEC Form 13F) and large-holder filings
(Schedules 13D and 13G), research only (Priority 8).

Every record keeps two dates apart: when the event happened (the transaction date, or the quarter end of
a 13F) and when it was disclosed (EDGAR's acceptance time). A record is usable only from its disclosure.

What these records are not:
- A 13F is a quarter-end snapshot of long positions in 13(f) securities, filed up to 45 days later. It
  leaves out short positions, most non-US holdings and cash, so it is never a complete or current
  portfolio, and a fund appearing in one is no evidence of skill.
- A Form 4 sale is often scheduled in advance under a Rule 10b5-1 plan, which the filing flags.
None of this feeds an order. It stays research only until a pre-registered test passes.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from defusedxml import ElementTree as SafeET

from ..core.timeutil import ensure_utc, from_micros, to_micros

CODES = {
    "P": "Open-market purchase", "S": "Open-market sale", "A": "Grant or award", "M": "Option exercise",
    "F": "Shares withheld for tax", "G": "Gift", "D": "Sold back to the issuer", "C": "Conversion",
    "X": "Option exercise", "J": "Other",
}
LARGE_HOLDER_FORMS = ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A")
_DDL = """
CREATE TABLE IF NOT EXISTS insider_transactions (
    accession VARCHAR NOT NULL, row_index INTEGER NOT NULL, issuer_cik VARCHAR NOT NULL, issuer_ticker VARCHAR,
    owner_cik VARCHAR, owner_name VARCHAR, role VARCHAR, plan_10b5_1 BOOLEAN, security VARCHAR, code VARCHAR,
    transaction_date DATE, disclosed_at BIGINT NOT NULL, shares DOUBLE, price DOUBLE, acquired_disposed VARCHAR,
    owned_after DOUBLE, direct_indirect VARCHAR, url VARCHAR NOT NULL, PRIMARY KEY (accession, row_index)
);
CREATE TABLE IF NOT EXISTS institutional_holdings (
    accession VARCHAR NOT NULL, manager_cik VARCHAR NOT NULL, manager_name VARCHAR, period_end DATE NOT NULL,
    disclosed_at BIGINT NOT NULL, cusip VARCHAR NOT NULL, issuer_name VARCHAR, title_of_class VARCHAR,
    value_usd DOUBLE, shares DOUBLE, share_type VARCHAR, put_call VARCHAR, url VARCHAR NOT NULL,
    PRIMARY KEY (accession, cusip, title_of_class, put_call)
);
CREATE TABLE IF NOT EXISTS large_holder_filings (
    accession VARCHAR PRIMARY KEY, issuer_cik VARCHAR NOT NULL, form VARCHAR NOT NULL, filed DATE, disclosed_at BIGINT NOT NULL,
    url VARCHAR NOT NULL
);
"""


def ensure_tables(conn) -> None:
    for stmt in _DDL.strip().split(";"):
        if stmt.strip():
            conn.execute(stmt).fetchall()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(node, path: str):
    """Path of local names, ignoring XML namespaces."""
    cur = [node]
    for part in path.split("/"):
        cur = [c for n in cur for c in n if _local(c.tag) == part]
        if not cur:
            return None
    return cur[0]


def _text(node, path: str) -> Optional[str]:
    el = _find(node, path)
    if el is None:
        return None
    if el.text and el.text.strip():
        return el.text.strip()
    v = _find(el, "value")
    return v.text.strip() if v is not None and v.text and v.text.strip() else None


def _num(s: Optional[str]) -> Optional[float]:
    try:
        return float(s.replace(",", "")) if s else None
    except ValueError:
        return None


def _flag(s: Optional[str]) -> bool:
    return (s or "").strip().lower() in ("1", "true")


def parse_form4(xml: bytes, accession: str, disclosed_at: datetime, url: str) -> list[dict]:
    """Non-derivative transactions only. Derivative rows (options, units) are counted but not stored."""
    root = SafeET.fromstring(xml)
    rel = _find(root, "reportingOwner/reportingOwnerRelationship")
    roles = []
    if rel is not None:
        if _flag(_text(rel, "isDirector")):
            roles.append("Director")
        if _flag(_text(rel, "isOfficer")):
            roles.append(_text(rel, "officerTitle") or "Officer")
        if _flag(_text(rel, "isTenPercentOwner")):
            roles.append("10% owner")
    base = {
        "accession": accession, "issuer_cik": _text(root, "issuer/issuerCik"), "issuer_ticker": _text(root, "issuer/issuerTradingSymbol"),
        "owner_cik": _text(root, "reportingOwner/reportingOwnerId/rptOwnerCik"),
        "owner_name": _text(root, "reportingOwner/reportingOwnerId/rptOwnerName"), "role": ", ".join(roles) or "Other",
        "plan_10b5_1": _flag(_text(root, "aff10b5One")), "disclosed_at": ensure_utc(disclosed_at), "url": url,
    }
    out = []
    table = _find(root, "nonDerivativeTable")
    for i, tx in enumerate([] if table is None else [t for t in table if _local(t.tag) == "nonDerivativeTransaction"]):
        d = _text(tx, "transactionDate")
        out.append({**base, "row_index": i, "security": _text(tx, "securityTitle"), "code": _text(tx, "transactionCoding/transactionCode"),
                    "transaction_date": date.fromisoformat(d[:10]) if d else None,
                    "shares": _num(_text(tx, "transactionAmounts/transactionShares")),
                    "price": _num(_text(tx, "transactionAmounts/transactionPricePerShare")),
                    "acquired_disposed": _text(tx, "transactionAmounts/transactionAcquiredDisposedCode"),
                    "owned_after": _num(_text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction")),
                    "direct_indirect": _text(tx, "ownershipNature/directOrIndirectOwnership")})
    return out


def parse_13f(xml: bytes) -> list[dict]:
    """Information table rows summed per security, class and put or call. Values are in whole dollars."""
    root = SafeET.fromstring(xml)
    agg: dict[tuple, dict] = {}
    for row in [r for r in root if _local(r.tag) == "infoTable"]:
        key = (_text(row, "cusip"), _text(row, "titleOfClass"), _text(row, "putCall") or "")
        a = agg.setdefault(key, {"cusip": key[0], "title_of_class": key[1], "put_call": key[2], "issuer_name": _text(row, "nameOfIssuer"),
                                 "value_usd": 0.0, "shares": 0.0, "share_type": _text(row, "shrsOrPrnAmt/sshPrnamtType")})
        a["value_usd"] += _num(_text(row, "value")) or 0.0
        a["shares"] += _num(_text(row, "shrsOrPrnAmt/sshPrnamt")) or 0.0
    return list(agg.values())


def _accepted(s: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


def ingest_insiders(client, cik: str, conn, limit: int = 40) -> dict:
    """Form 4 filings in the issuer's EDGAR filing list. Safe to rerun."""
    ensure_tables(conn)
    r = client.submissions(cik)["filings"]["recent"]
    added = seen = 0
    for i, form in enumerate(r["form"]):
        if form in LARGE_HOLDER_FORMS:
            acc = r["accessionNumber"][i]
            url = f"{client.cfg.archives_base_url}/{int(cik)}/{acc.replace('-', '')}/"
            conn.execute("INSERT OR IGNORE INTO large_holder_filings VALUES (?,?,?,?,?,?)",
                         [acc, str(cik).zfill(10), form, r["filingDate"][i], to_micros(_accepted(r["acceptanceDateTime"][i])), url]).fetchall()
        if form != "4" or seen >= limit:
            continue
        seen += 1
        acc = r["accessionNumber"][i]
        name = r["primaryDocument"][i].rsplit("/", 1)[-1]  # the raw XML, not the XSL-rendered view
        url = f"{client.cfg.archives_base_url}/{int(cik)}/{acc.replace('-', '')}/{name}"
        if conn.execute("SELECT count(*) FROM insider_transactions WHERE accession = ?", [acc]).fetchall()[0][0]:
            continue
        for row in parse_form4(client.document(cik, acc, name), acc, _accepted(r["acceptanceDateTime"][i]), url):
            conn.execute("INSERT OR IGNORE INTO insider_transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                row["accession"], row["row_index"], row["issuer_cik"], row["issuer_ticker"], row["owner_cik"], row["owner_name"],
                row["role"], row["plan_10b5_1"], row["security"], row["code"], row["transaction_date"], to_micros(row["disclosed_at"]),
                row["shares"], row["price"], row["acquired_disposed"], row["owned_after"], row["direct_indirect"], row["url"]]).fetchall()
            added += 1
    return {"form4_filings_read": seen, "transactions_added": added}


def ingest_13f(client, manager_cik: str, conn) -> dict:
    """The manager's latest 13F-HR. The information table is the XML file that is not the cover page."""
    ensure_tables(conn)
    subs = client.submissions(manager_cik)
    r = subs["filings"]["recent"]
    idx = next((i for i, f in enumerate(r["form"]) if f in ("13F-HR", "13F-HR/A")), None)
    if idx is None:
        return {"status": "NOT AVAILABLE", "reason": "No 13F-HR in the manager's filing list"}
    acc = r["accessionNumber"][idx]
    folder = acc.replace("-", "")
    listing = json.loads(client.t.get_bytes(f"{client.cfg.archives_base_url}/{int(manager_cik)}/{folder}/index.json"))
    files = [x["name"] for x in listing["directory"]["item"] if x["name"].endswith(".xml") and x["name"] != "primary_doc.xml"]
    if not files:
        return {"status": "NOT AVAILABLE", "reason": "No information table in the filing"}
    rows = parse_13f(client.document(manager_cik, acc, files[0]))
    url = f"{client.cfg.archives_base_url}/{int(manager_cik)}/{folder}/{files[0]}"
    when = to_micros(_accepted(r["acceptanceDateTime"][idx]))
    for h in rows:
        conn.execute("INSERT OR IGNORE INTO institutional_holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            acc, str(manager_cik).zfill(10), subs.get("name"), r["reportDate"][idx], when, h["cusip"], h["issuer_name"],
            h["title_of_class"], h["value_usd"], h["shares"], h["share_type"], h["put_call"], url]).fetchall()
    return {"status": "OK", "accession": acc, "period_end": r["reportDate"][idx], "holdings": len(rows)}


def _rows(conn, sql: str, args: list) -> list[dict]:
    try:
        cur = conn.execute(sql, args)
    except Exception:
        return []  # tables not created yet
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def insiders_as_of(conn, when: datetime, ticker: Optional[str] = None) -> list[dict]:
    rows = _rows(conn, "SELECT * FROM insider_transactions WHERE disclosed_at < ?" + (" AND upper(issuer_ticker) = ?" if ticker else "")
                 + " ORDER BY disclosed_at DESC, row_index", [to_micros(ensure_utc(when))] + ([ticker.upper()] if ticker else []))
    for r in rows:
        disclosed = from_micros(r["disclosed_at"])
        r["disclosed_at"] = disclosed.isoformat()
        r["transaction_date"] = r["transaction_date"].isoformat() if r["transaction_date"] else None
        r["disclosure_lag_days"] = (disclosed.date() - date.fromisoformat(r["transaction_date"])).days if r["transaction_date"] else None
        r["meaning"] = CODES.get(r["code"] or "", "Not described")
        r["value_usd"] = r["shares"] * r["price"] if r["shares"] and r["price"] else None
    return rows


def holdings_as_of(conn, when: datetime) -> list[dict]:
    """Latest disclosed 13F per manager, as filed. Never a current or complete portfolio."""
    rows = _rows(conn, "SELECT * FROM institutional_holdings WHERE disclosed_at < ? ORDER BY manager_cik, value_usd DESC",
                 [to_micros(ensure_utc(when))])
    latest: dict[str, str] = {}
    for r in rows:
        latest.setdefault(r["manager_cik"], r["accession"])
    out = [r for r in rows if latest[r["manager_cik"]] == r["accession"]]
    for r in out:
        r["disclosed_at"] = from_micros(r["disclosed_at"]).isoformat()
        r["period_end"] = r["period_end"].isoformat()
    return out


def large_holders_as_of(conn, when: datetime, issuer_cik: Optional[str] = None) -> list[dict]:
    rows = _rows(conn, "SELECT * FROM large_holder_filings WHERE disclosed_at < ?" + (" AND issuer_cik = ?" if issuer_cik else "")
                 + " ORDER BY disclosed_at DESC", [to_micros(ensure_utc(when))] + ([str(issuer_cik).zfill(10)] if issuer_cik else []))
    for r in rows:
        r["disclosed_at"] = from_micros(r["disclosed_at"]).isoformat()
        r["filed"] = r["filed"].isoformat() if r["filed"] else None
    return rows
