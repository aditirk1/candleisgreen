"""As-known-then replay (spec Teaching). Every read goes through the replay clock.

Prices come from the point-in-time store and news from the news store, both filtered to
values usable strictly before the cursor, so a replay can never see later news, later
prices or later corrections at an earlier time. Intraday data does not exist on the free
plan, and the replay says so instead of inventing it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..core.timeutil import ensure_utc
from ..data.instruments import InstrumentMaster
from ..data.pit_store import PointInTimeStore
from ..sources.rss import NewsStore


@dataclass
class Replay:
    store: PointInTimeStore
    news: NewsStore
    master: InstrumentMaster
    cursor: datetime
    end: datetime
    history: list = field(default_factory=list)

    def __post_init__(self):
        self.cursor = ensure_utc(self.cursor)
        self.end = ensure_utc(self.end)

    def advance(self, step: timedelta = timedelta(days=1)) -> datetime:
        if self.cursor + step > self.end:
            raise ValueError("the replay cannot move past its end")
        self.history.append(self.cursor)
        self.cursor = self.cursor + step
        return self.cursor

    def prices(self, symbol: str, field_name: str = "close", last: int = 30) -> list[dict]:
        iid = self.master.instrument_for_symbol(symbol)
        if iid is None:
            return []
        rows = self.store.as_of(self.cursor).series(iid, field_name)[-last:]
        return [{"date": o.event_time.date().isoformat(), "value": o.value, "usable_from": o.first_usable_at.isoformat(),
                 "vintage": o.vintage} for o in rows]

    def headlines(self, ticker: Optional[str] = None, limit: int = 20) -> list[dict]:
        return [{"title": n.title, "feed": n.feed, "usable_from": n.first_usable_at.isoformat(), "link": n.link,
                 "cluster_id": n.cluster_id} for n in self.news.as_of(self.cursor, ticker=ticker, limit=limit)]

    def view(self, symbol: str) -> dict:
        return {"cursor": self.cursor.isoformat(), "symbol": symbol, "prices": self.prices(symbol),
                "news": self.headlines(), "intraday": "NOT AVAILABLE. The free data plan has daily bars only"}
