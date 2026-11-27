"""Research Capture Inbox (spec section Social platforms, realistically).

Aditi pastes a link, text or a file. The inbox stores a SHA-256 hash of what was given, the time,
and a short summary. It never keeps the full copied content. Sentences that state a testable claim
or a forecast become claim cards, which the nightly research loop picks up. Commentary is kept as
a capture but is never scored.

Links are never fetched unless their host is in `research.inbox.auto_fetch_hosts`, which is empty
by default. A link that cannot be fetched shows a request for input: paste the passage that holds
the claim. Files that cannot be read as text (for example PDF) get the same request.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..core.config import InboxConfig
from ..core.ids import make_id
from ..core.sqlite_shared import connect as sqlite_connect
from ..core.timeutil import iso_utc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    capture_id TEXT PRIMARY KEY, kind TEXT NOT NULL, capture_hash TEXT NOT NULL, received_at TEXT NOT NULL,
    url TEXT, filename TEXT, summary TEXT, status TEXT NOT NULL, request TEXT, cards_json TEXT NOT NULL,
    sent_to_factory INTEGER NOT NULL DEFAULT 0
);
"""
TEXT_FILES = (".txt", ".md", ".csv", ".htm", ".html")

# Words that mark a statement about returns or prices, and words that give it a direction.
_TARGET = re.compile(r"\b(returns?|outperform\w*|underperform\w*|premium|alpha|abnormal|excess return|anomal\w+|"
                     r"predicts?|forecasts?|drift|spread|earnings surprise|sharpe)\b", re.I)
_UP = re.compile(r"\b(higher|positive|outperform\w*|rise|rises|increase\w*|beat\w*|earn\w* more|premium)\b", re.I)
_DOWN = re.compile(r"\b(lower|negative|underperform\w*|fall|falls|decline\w*|decrease\w*|earn\w* less)\b", re.I)
_HORIZON = re.compile(r"\b(\d+)[- ](day|week|month|quarter|year)s?\b", re.I)
_FUTURE = re.compile(r"\b(will|expect\w*|by (?:the )?end of|next (?:week|month|quarter|year))\b", re.I)
_TICKER = re.compile(r"(?:\$([A-Z]{1,5})\b)|\b([A-Z]{2,5})(?= (?:shares|stock))")
_PROB = re.compile(r"\b(\d{1,3})\s?(?:%|percent) (?:chance|probability|likely)\b", re.I)


class InboxError(ValueError):
    pass


def sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z$])", text) if s.strip()]


def summarize(text: str, max_chars: int) -> str:
    """The opening sentences, up to the limit. Never the full text of a long capture."""
    out = ""
    for s in sentences(text):
        if len(out) + len(s) + 1 > max_chars:
            break
        out = f"{out} {s}".strip()
    return out or text[:max_chars].rsplit(" ", 1)[0]


def extract_claims(text: str, capture_hash: str, received_at: datetime, url: Optional[str]) -> list[dict]:
    """Rule-based extraction. Each claim sentence becomes a card. Nothing is inferred beyond the words."""
    cards = []
    for s in sentences(text):
        if not _TARGET.search(s):
            continue
        up, down = bool(_UP.search(s)), bool(_DOWN.search(s))
        direction = "positive" if up and not down else "negative" if down and not up else None
        if direction is None:
            continue  # no clear direction, so not testable as stated
        tickers = sorted({a or b for a, b in _TICKER.findall(s)})
        h = _HORIZON.search(s)
        p = _PROB.search(s)
        kind = "forecast" if tickers and _FUTURE.search(s) else "testable_claim"
        cards.append({
            "source_type": "capture", "claim_type": kind, "title": s[:160], "definition": s[:400],
            "canonical_url": url, "market": "US equities" if tickers else None, "instruments": tickers,
            "target": "return", "direction": direction, "horizon": f"{h.group(1)} {h.group(2).lower()}" if h else None,
            "probability_if_stated": int(p.group(1)) / 100 if p else None, "data_required": [],
            "study_type": "forecast" if kind == "forecast" else "new_factor", "evidence_label": "unreplicated", "peer_review_status": "unknown",
            "license": "user_capture", "capture_hash": capture_hash, "first_actionable_at": iso_utc(received_at),
        })
    return cards


def _file_text(filename: str, content_b64: str, max_bytes: int) -> tuple[Optional[str], bytes]:
    raw = base64.b64decode(content_b64, validate=True)
    if len(raw) > max_bytes:
        raise InboxError(f"file is larger than {max_bytes} bytes")
    if Path(filename).suffix.lower() not in TEXT_FILES:
        return None, raw
    text = raw.decode("utf-8", errors="replace")
    if Path(filename).suffix.lower() in (".htm", ".html"):
        text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", text)))
    return text, raw


class Inbox:
    def __init__(self, path: str | Path, cfg: InboxConfig, shared_across_threads: bool = False):
        self.cfg = cfg
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def capture(self, kind: str, now: datetime, content: str = "", url: Optional[str] = None,
                filename: Optional[str] = None) -> dict:
        if kind not in ("link", "text", "file"):
            raise InboxError("kind must be link, text or file")
        text, request, status = None, None, "EXTRACTED"
        if kind == "link":
            parsed = urlparse(url or content)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise InboxError("a link needs an http or https URL")
            url = parsed.geturl()
            raw = url.encode()
            if parsed.hostname not in self.cfg.auto_fetch_hosts:
                status = "NEEDS INPUT"
                request = (f"Automatic retrieval is not allowed for {parsed.hostname}. "
                           "Paste the abstract or the passage that states the claim as text.")
            text = content if content and content != url else None
        elif kind == "text":
            if not content.strip():
                raise InboxError("empty text")
            text, raw = content, content.encode("utf-8")
        else:
            if not filename:
                raise InboxError("a file needs its name")
            text, raw = _file_text(filename, content, self.cfg.max_file_bytes)
            if text is None:
                status = "NEEDS INPUT"
                request = f"{Path(filename).suffix or 'This'} files are not read automatically. Paste the abstract or key passage as text."
        digest = hashlib.sha256(raw).hexdigest()
        existing = self.conn.execute("SELECT capture_id FROM captures WHERE capture_hash = ?", (digest,)).fetchall()
        if existing:
            return {**self.get(existing[0][0]), "duplicate": True}
        cards = extract_claims(text, digest, now, url) if text else []
        if text and not cards and status == "EXTRACTED":
            status = "NO CLAIM FOUND"
            request = "No sentence states a return or price effect with a direction. Paste the sentence that does, if there is one."
        summary = summarize(text, self.cfg.summary_max_chars) if text else None
        cid = make_id("cap", {"hash": digest})
        self.conn.execute("INSERT INTO captures VALUES (?,?,?,?,?,?,?,?,?,?,0)",
                          (cid, kind, digest, iso_utc(now), url, filename, summary, status, request, json.dumps(cards)))
        return {**self.get(cid), "duplicate": False}

    def get(self, capture_id: str) -> dict:
        rows = self.conn.execute("SELECT * FROM captures WHERE capture_id = ?", (capture_id,)).fetchall()
        if not rows:
            raise KeyError(capture_id)
        return self._row(rows[0])

    @staticmethod
    def _row(r) -> dict:
        keys = ("capture_id", "kind", "capture_hash", "received_at", "url", "filename", "summary", "status", "request",
                "cards", "sent_to_factory")
        d = dict(zip(keys, r))
        d["cards"] = json.loads(d["cards"])
        d["sent_to_factory"] = bool(d["sent_to_factory"])
        return d

    def list(self, limit: int = 100) -> list[dict]:
        return [self._row(r) for r in self.conn.execute(
            "SELECT * FROM captures ORDER BY received_at DESC LIMIT ?", (limit,)).fetchall()]

    def take_for_factory(self) -> list[dict]:
        """Claim cards not yet given to the research loop. Commentary never reaches it."""
        rows = self.conn.execute("SELECT capture_id, cards_json FROM captures WHERE sent_to_factory = 0").fetchall()
        cards = []
        for cid, cj in rows:
            cards += [c for c in json.loads(cj) if c["claim_type"] in ("testable_claim", "forecast")]
            self.conn.execute("UPDATE captures SET sent_to_factory = 1 WHERE capture_id = ?", (cid,))
        return cards
