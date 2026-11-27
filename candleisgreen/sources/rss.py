"""Lawful RSS ingestion (spec Phase 4). Official feeds only, parsed with defusedxml.

Each item keeps a content hash, its publication time, the time the platform first saw it,
and `first_usable_at`, which is never earlier than the time it was first seen. Only a short
summary is stored. Near-duplicate stories are clustered by title similarity.
"""
from __future__ import annotations

import hashlib
import html
import re
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Optional

from defusedxml import ElementTree as SafeET

from ..core.sqlite_shared import connect as sqlite_connect
from ..core.config import AppConfig, FeedConfig
from ..core.ids import make_id
from ..core.timeutil import ensure_utc, from_micros, to_micros

_TICKER = re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|NYSEARCA|NYSE American|AMEX)\s*:\s*([A-Z][A-Z.]{0,5})\)")
_WORD = re.compile(r"[a-z0-9]+")
_TAG = re.compile(r"<[^>]+>")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_items (
    item_id TEXT PRIMARY KEY, feed TEXT NOT NULL, title TEXT NOT NULL, link TEXT NOT NULL, summary TEXT NOT NULL,
    content_hash TEXT NOT NULL, published_at INTEGER, first_seen_at INTEGER NOT NULL, first_usable_at INTEGER NOT NULL,
    tickers TEXT NOT NULL, cluster_id TEXT NOT NULL, license TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_usable ON news_items(first_usable_at);
"""


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    feed: str
    title: str
    link: str
    summary: str
    content_hash: str
    published_at: Optional[datetime]
    first_seen_at: datetime
    first_usable_at: datetime
    tickers: tuple[str, ...]
    cluster_id: str
    license: str


def _text(node, tag: str) -> str:
    el = node.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def _clean(text: str, limit: int) -> str:
    plain = html.unescape(_TAG.sub(" ", text))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit]


def parse_feed(xml_bytes: bytes, feed: FeedConfig, seen_at: datetime, max_summary: int) -> list[dict]:
    """RSS 2.0 items. Malformed or hostile XML raises and the feed is skipped."""
    root = SafeET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = _clean(_text(item, "title"), 300)
        link = _text(item, "link")
        guid = _text(item, "guid") or link or title
        summary = _clean(_text(item, "description"), max_summary)
        pub = _text(item, "pubDate")
        try:
            published = ensure_utc(parsedate_to_datetime(pub)) if pub else None
        except (TypeError, ValueError):
            published = None
        out.append({"guid": guid, "title": title, "link": link, "summary": summary, "published_at": published,
                    "tickers": tuple(sorted(set(_TICKER.findall(f"{title} {summary}"))))})
    return out


def _words(title: str) -> set[str]:
    return {w for w in _WORD.findall(title.lower()) if len(w) > 2}


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


class NewsStore:
    def __init__(self, path: str | Path, shared_across_threads: bool = False):
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def _cluster_for(self, title: str, when: datetime, cfg: AppConfig) -> str:
        lo = to_micros(when - timedelta(hours=cfg.news.cluster_window_hours))
        hi = to_micros(when + timedelta(hours=cfg.news.cluster_window_hours))
        best, best_sim = None, 0.0
        for cid, other in self.conn.execute(
                "SELECT cluster_id, title FROM news_items WHERE first_usable_at BETWEEN ? AND ?", (lo, hi)).fetchall():
            sim = similarity(title, other)
            if sim > best_sim:
                best, best_sim = cid, sim
        return best if best and best_sim >= cfg.news.cluster_similarity else make_id("story", {"title": title, "at": when})

    def add(self, feed: FeedConfig, items: Iterable[dict], seen_at: datetime, cfg: AppConfig) -> int:
        seen_at = ensure_utc(seen_at)
        added = 0
        for it in items:
            iid = make_id("news", {"feed": feed.name, "guid": it["guid"]})
            if self.conn.execute("SELECT 1 FROM news_items WHERE item_id = ?", (iid,)).fetchone():
                continue
            usable = max(seen_at, it["published_at"] or seen_at)  # never usable before the platform saw it
            digest = hashlib.sha256(f"{it['title']}\n{it['summary']}\n{it['link']}".encode()).hexdigest()
            cluster = self._cluster_for(it["title"], usable, cfg)
            self.conn.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                iid, feed.name, it["title"], it["link"], it["summary"], digest,
                to_micros(it["published_at"]) if it["published_at"] else None, to_micros(seen_at), to_micros(usable),
                ",".join(it["tickers"]), cluster, feed.license))
            added += 1
        return added

    def as_of(self, when: datetime, ticker: Optional[str] = None, limit: int = 200,
              since: Optional[datetime] = None) -> list[NewsItem]:
        """Only items usable strictly before `when`. This is the only read path for models and replay."""
        sql = "SELECT * FROM news_items WHERE first_usable_at < ?"
        args: list = [to_micros(ensure_utc(when))]
        if since is not None:
            sql += " AND first_usable_at >= ?"
            args.append(to_micros(ensure_utc(since)))
        if ticker:
            sql += " AND (',' || tickers || ',') LIKE ?"
            args.append(f"%,{ticker},%")
        rows = self.conn.execute(sql + " ORDER BY first_usable_at DESC LIMIT ?", args + [limit]).fetchall()
        return [NewsItem(r[0], r[1], r[2], r[3], r[4], r[5], from_micros(r[6]) if r[6] is not None else None,
                         from_micros(r[7]), from_micros(r[8]), tuple(t for t in r[9].split(",") if t), r[10], r[11])
                for r in rows]

    def clusters(self, when: datetime, since: Optional[datetime] = None) -> list[dict]:
        items = self.as_of(when, since=since, limit=1000)
        groups: dict[str, list[NewsItem]] = {}
        for it in items:
            groups.setdefault(it.cluster_id, []).append(it)
        return [{"cluster_id": cid, "headline": g[-1].title, "items": len(g), "feeds": sorted({x.feed for x in g}),
                 "first_usable_at": min(x.first_usable_at for x in g).isoformat(), "tickers": sorted({t for x in g for t in x.tickers}),
                 "links": [x.link for x in g], "summary": max((x.summary for x in g), key=len)} for cid, g in groups.items()]


def fetch(feed: FeedConfig, user_agent: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(feed.url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def ingest(feed: FeedConfig, xml_bytes: bytes, store: NewsStore, seen_at: datetime, cfg: AppConfig) -> int:
    return store.add(feed, parse_feed(xml_bytes, feed, seen_at, cfg.news.max_summary_chars), seen_at, cfg)
