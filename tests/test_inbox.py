"""Research Capture Inbox: hash and time, summaries only, claims extracted, input requested when retrieval is not allowed."""
import base64
import hashlib
from datetime import datetime, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.research.inbox import Inbox, InboxError, extract_claims

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)
TEXT = ("We study firms with high gross profitability. "
        "Stocks with high gross profitability earn higher average returns than unprofitable firms over the next 12 months. "
        "The market was volatile in the sample. "
        "We think $ACME shares will outperform the index by the end of next quarter, a 70% chance in our view. "
        + "Filler sentence about the data set and its construction. " * 40)


@pytest.fixture
def inbox(tmp_path):
    box = Inbox(tmp_path / "inbox.sqlite", load_config().research.inbox)
    yield box
    box.close()


def test_text_capture_keeps_hash_time_summary_and_claims_only(inbox):
    out = inbox.capture("text", NOW, TEXT)
    assert out["capture_hash"] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert out["received_at"].startswith("2026-11-24T15:00")
    assert len(out["summary"]) <= 600 and len(out["summary"]) < len(TEXT) / 3
    kinds = sorted(c["claim_type"] for c in out["cards"])
    assert kinds == ["forecast", "testable_claim"]
    forecast = next(c for c in out["cards"] if c["claim_type"] == "forecast")
    assert forecast["instruments"] == ["ACME"] and forecast["direction"] == "positive"
    assert forecast["probability_if_stated"] == 0.7
    claim = next(c for c in out["cards"] if c["claim_type"] == "testable_claim")
    assert claim["horizon"] == "12 month" and claim["capture_hash"] == out["capture_hash"]
    assert all(c["license"] == "user_capture" and c["evidence_label"] == "unreplicated" for c in out["cards"])
    assert inbox.capture("text", NOW, TEXT)["duplicate"] is True


def test_full_text_is_never_stored(inbox, tmp_path):
    inbox.capture("text", NOW, TEXT)
    raw = (tmp_path / "inbox.sqlite").read_bytes()
    assert b"Filler sentence about the data set and its construction. " * 12 not in raw
    assert b"Filler sentence" in raw  # the short summary is kept


def test_link_asks_for_input_instead_of_fetching(inbox):
    out = inbox.capture("link", NOW, url="https://papers.example.org/abstract=123")
    assert out["status"] == "NEEDS INPUT" and "papers.example.org" in out["request"] and out["cards"] == []
    with pytest.raises(InboxError):
        inbox.capture("link", NOW, url="ftp://example.org/x")


def test_files_text_read_and_pdf_needs_input(inbox):
    html = "<html><script>x()</script><p>Small firms earn higher returns in January.</p></html>"
    out = inbox.capture("file", NOW, base64.b64encode(html.encode()).decode(), filename="note.html")
    assert out["status"] == "EXTRACTED" and len(out["cards"]) == 1 and "x()" not in (out["summary"] or "")
    pdf = inbox.capture("file", NOW, base64.b64encode(b"%PDF-1.7 binary").decode(), filename="paper.pdf")
    assert pdf["status"] == "NEEDS INPUT" and "Paste" in pdf["request"]


def test_commentary_without_direction_is_not_a_claim():
    assert extract_claims("Markets were busy today. Returns are interesting to study.", "h", NOW, None) == []


def test_nightly_review_takes_claims_once(tmp_path):
    from candleisgreen.core.audit import AuditLog
    from candleisgreen.research.registry import ResearchRegistry
    from candleisgreen.scheduler import _review

    cfg = load_config()
    box = Inbox(tmp_path / "inbox.sqlite", cfg.research.inbox)
    box.capture("text", NOW, TEXT)
    box.close()
    first = _review(NOW, tmp_path, cfg, True)
    again = _review(NOW, tmp_path, cfg, True)
    assert (first["captured_claims"], again["captured_claims"]) == (2, 0)
    reg = ResearchRegistry(tmp_path / "research.sqlite", AuditLog(tmp_path / "audit.sqlite"))
    assert len([c for c in reg.claims() if c["card"].get("source_type") == "capture"]) == 2
    reg.close()


def test_inbox_through_the_api(tmp_path):
    from fastapi.testclient import TestClient

    from candleisgreen.api.app import create_app

    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", load_config(), clock=lambda: NOW))
    assert api.post("/api/inbox", json={"kind": "text", "content": TEXT}).json()["status"] == "EXTRACTED"
    assert api.post("/api/inbox", json={"kind": "text", "content": "  "}).status_code == 400
    assert len(api.get("/api/inbox").json()["captures"]) == 1
