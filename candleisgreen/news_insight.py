"""Turns a news cluster into something readable at a glance (spec News: what happened, why it may
matter and what prices did, kept separate).

- What happened: the headline, plus the feed's own summary when it says more than the headline.
- Why it may matter: a category from `config/news_rules.yaml`. Its text is a general description.
- Who it names: companies matched by name against SEC entity names and SEC's company ticker list.
  Only full company names count, and the match must start with a capital letter in the text.
- What prices did: the next recorded close after the story became usable, for each named company in
  the recorded data, beside the equal-weighted move of all recorded names. An observation, never a
  claim of cause.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .core.timeutil import ensure_utc
from .data.instruments import InstrumentMaster
from .sources.trials import normalize

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config" / "news_rules.yaml"
TICKERS_FIXTURE = ROOT / "tests" / "fixtures" / "sec" / "www.sec.gov__files__company_tickers.json"
_STOP = {"bank", "capital", "financial", "group", "trust", "national", "american", "first", "global", "united", "federal"}


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())["categories"]


def classify(text: str, rules: list[dict]) -> Optional[dict]:
    low = text.lower()
    for r in rules:
        if any(m.lower() in low for m in r["match"]):
            return {k: r[k] for k in ("id", "label", "what_it_is", "can_affect")}
    return None


def classify_story(text: str, feeds: list[str], rules: list[dict]) -> Optional[dict]:
    """Words first, then a feed whose every item is one kind of news."""
    hit = classify(text, rules)
    if hit:
        return hit
    for r in rules:
        if set(r.get("feeds", [])) & set(feeds):
            return {k: r[k] for k in ("id", "label", "what_it_is", "can_affect")}
    return None


@dataclass
class CompanyIndex:
    names: dict[str, str]  # normalized name to ticker

    @classmethod
    def build(cls, tickers_json: Optional[Path], master: Optional[InstrumentMaster] = None) -> "CompanyIndex":
        names: dict[str, str] = {}
        if tickers_json and Path(tickers_json).exists():
            for row in json.loads(Path(tickers_json).read_text()).values():
                n = normalize(row["title"])
                if n:
                    names.setdefault(n, row["ticker"])
        if master is not None:
            for iid, name in master.entity_names():
                syms = master.symbols(iid)
                n = normalize(name)
                if n and syms:
                    names.setdefault(n, syms[-1])
        # A one-word name must be long and not a common word, or it would match ordinary text.
        names = {n: t for n, t in names.items() if " " in n or (len(n) >= 5 and n not in _STOP)}
        return cls(names)

    def __post_init__(self):
        self.by_first: dict[str, list[str]] = {}
        for n in self.names:
            self.by_first.setdefault(n.split()[0], []).append(n)

    def link(self, text: str) -> list[str]:
        norm = normalize(text)
        padded = f" {norm} "
        found = set()
        for word in set(norm.split()):
            for n in self.by_first.get(word, ()):
                if f" {n} " not in padded:
                    continue
                pattern = r"\b" + r"[^A-Za-z0-9]+".join(re.escape(w) for w in n.split()) + r"\b"
                if any(m.group(0)[0].isupper() for m in re.finditer(pattern, text, re.I)):
                    found.add(self.names[n])
        return sorted(found)


def _move(series: list[tuple[datetime, float]], when: datetime) -> Optional[tuple[str, float]]:
    before = [v for t, v in series if t < when]
    after = [(t, v) for t, v in series if t >= when]
    if not before or not after or not before[-1]:
        return None
    return after[0][0].date().isoformat(), after[0][1] / before[-1] - 1


def load_closes(store, start: datetime, now: datetime) -> dict[str, list[tuple[datetime, float]]]:
    """All closes from `start` to `now` that were usable by `now`, loaded once per request."""
    return store.as_of(ensure_utc(now)).values_between("close", start, ensure_utc(now))


def price_moves(closes: dict, master: InstrumentMaster, tickers: list[str], when: datetime,
                market_cache: Optional[dict] = None) -> dict:
    """Next recorded close after `when` for each linked ticker, and for all recorded names."""
    when = ensure_utc(when)
    out = {"tickers": [], "market": None}
    for t in tickers:
        iid = master.instrument_for_symbol(t)
        mv = _move(closes.get(iid, []), when) if iid else None
        out["tickers"].append({"ticker": t, "session": mv[0], "move": mv[1]} if mv else
                              {"ticker": t, "session": None, "move": None,
                               "reason": "not in the recorded data" if not iid else "no close after the story yet"})
    key = when.isoformat()
    if market_cache is not None and key in market_cache:
        out["market"] = market_cache[key]
        return out
    moves = [m for s in closes.values() if (m := _move(s, when))]
    if moves:
        session = min(s for s, _ in moves)
        same = [r for s, r in moves if s == session]
        out["market"] = {"session": session, "move": sum(same) / len(same), "names": len(same)}
    if market_cache is not None:
        market_cache[key] = out["market"]
    return out
