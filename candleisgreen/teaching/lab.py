"""Teaching tools built from recorded facts (spec Teaching table).

- Market autopsy: after each simulated fill, the expected catalyst, what happened, the spread
  paid, a profit and loss split, and which assumptions failed.
- Counterfactual: change one input and see whether the decision changes. Always HYPOTHETICAL.
- Spaced review: cards from the user's own wrong predictions first, then glossary terms, on a
  fixed interval ladder. A replay outcome never appears before the replay clock reveals it.
- Crisis library: each episode shows NOT AVAILABLE until stored price data covers its dates.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.config import AppConfig
from ..core.ids import make_id
from ..core.sqlite_shared import connect as sqlite_connect
from ..core.timeutil import ensure_utc, from_micros, iso_utc, to_micros
from ..data.adjust import adjust_closes
from ..data.instruments import InstrumentMaster
from ..data.pit_store import PointInTimeStore
from ..models import ts_momentum

HYPOTHETICAL = "HYPOTHETICAL"


# Market autopsy --------------------------------------------------------------------------------

def _forecasts(audit_records: list[dict]) -> dict[str, dict]:
    out = {}
    for r in audit_records:
        if r["event_type"] == "forecast_issued":
            out[r["entity_id"]] = json.loads(r["payload_json"])
    return out


def _close_on_or_before(store: PointInTimeStore, iid: str, when: datetime, known_by: datetime) -> Optional[tuple]:
    obs = [o for o in store.as_of(known_by).series(iid, "close") if o.event_time <= when]
    return (obs[-1].event_time, obs[-1].value) if obs else None


def _market_return(store: PointInTimeStore, start: datetime, end: datetime, known_by: datetime,
                   master: InstrumentMaster) -> Optional[float]:
    """Equal-weighted mean return of recorded instruments with closes at both dates."""
    rets = []
    view = store.as_of(known_by)
    for inst in master.instruments():
        s = view.series(inst["instrument_id"], "close")
        a = [o.value for o in s if o.event_time <= start]
        b = [o.value for o in s if o.event_time <= end]
        if a and b and a[-1] > 0:
            rets.append(b[-1] / a[-1] - 1)
    return sum(rets) / len(rets) if rets else None


def autopsy(journal, audit_records: list[dict], store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig,
            now: datetime) -> list[dict]:
    now = ensure_utc(now)
    forecasts = _forecasts(audit_records)
    by_order = {p.client_order_id: p for p in journal.proposals() if p.client_order_id}
    out = []
    for f in journal.fills():
        p = by_order.get(f["client_order_id"])
        if p is None:
            continue
        fc = forecasts.get(p.forecast_id, {})
        filled_at = datetime.fromisoformat(f["filled_at"])
        target_end = datetime.fromisoformat(fc["target_end"]) if fc.get("target_end") else filled_at + timedelta(days=30)
        sign = 1 if f["side"] == "buy" else -1
        bps = f["slippage_bps"]
        mid = f["price"] / (1 + sign * bps / 1e4) if bps is not None else None
        spread_cost = abs(f["price"] - mid) * f["quantity"] if mid else None
        open_trade = now < target_end
        end = _close_on_or_before(store, f["instrument_id"], min(now, target_end), now)
        if end is not None and end[0].date() < filled_at.date():
            end = None  # the latest close is from before the fill
        row = {
            "fill_id": f["fill_id"], "symbol": p.symbol, "side": f["side"], "quantity": f["quantity"],
            "filled_at": f["filled_at"], "fill_price": f["price"], "model": f"{p.model_id} {p.model_version}",
            "expected_catalyst": _catalyst(p.model_id, cfg),
            "window": {"start": fc.get("target_start"), "end": target_end.isoformat(),
                       "status": "OPEN" if open_trade else "CLOSED"},
            "spread_paid_bps": bps, "spread_paid_usd": spread_cost,
        }
        if end is None or mid is None:
            row.update({"what_happened": "NOT AVAILABLE. No recorded close after the fill", "pnl": None, "assumptions": []})
            out.append(row)
            continue
        end_time, end_price = end
        move = sign * (end_price - mid) * f["quantity"]
        mkt = _market_return(store, filled_at, end_time, now, master)
        market_part = sign * mid * f["quantity"] * mkt if mkt is not None else None
        ret = end_price / mid - 1
        row["what_happened"] = (f"{p.symbol} moved {ret * 100:+.2f}% from the arrival midpoint to {end_price:.2f} "
                                f"by {end_time.date().isoformat()}")
        row["pnl"] = {
            "total_usd": move - (spread_cost or 0.0), "price_move_usd": move, "spread_cost_usd": -(spread_cost or 0.0),
            "market_usd": market_part, "specific_usd": move - market_part if market_part is not None else None,
            "market_method": "equal-weighted recorded instruments over the same dates, beta assumed 1",
        }
        modeled_bps = cfg.research.default_half_spread * 1e4
        row["assumptions"] = [
            {"assumption": "The trend continues in the trade's direction", "result":
             "NOT YET. The window is open" if open_trade else ("HELD" if sign * ret > 0 else "FAILED")},
            {"assumption": f"Spread paid at most the modeled {modeled_bps:.1f} bps", "result":
             "HELD" if bps is not None and abs(bps) <= modeled_bps + 1e-6 else "FAILED"},  # tolerance for rounding
        ]
        out.append(row)
    return out


def _catalyst(model_id: str, cfg: AppConfig) -> str:
    if model_id.startswith("ts_momentum"):
        m = cfg.models.ts_momentum
        return (f"No event. The model expects the {m.lookback_days}-day trend, skipping the last {m.skip_days} days, "
                "to continue over the next month")
    return "NOT AVAILABLE. The model records no catalyst"


# Counterfactual --------------------------------------------------------------------------------

def counterfactual(store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig, symbol: str, when: datetime,
                   change: str, amount: float) -> dict:
    """Change one input of the active trend model or the risk check. Nothing is stored or traded."""
    iid = master.instrument_for_symbol(symbol)
    if iid is None:
        return {"label": HYPOTHETICAL, "status": "NOT AVAILABLE", "reason": f"{symbol} is not in the instrument master"}
    obs = store.as_of(when).series(iid, "close")
    closes = [c for _, c in adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(iid), when.date())]
    m = cfg.models.ts_momentum
    base = ts_momentum.score(closes, m)
    if base is None:
        return {"label": HYPOTHETICAL, "status": "NOT AVAILABLE", "reason": "not enough price history for the trend model"}

    def decision(s: Optional[float]) -> str:
        return "BUY" if s is not None and s > 0 else "NO BUY"

    out = {"label": HYPOTHETICAL, "status": "OK", "symbol": symbol, "as_of": ensure_utc(when).isoformat(),
           "change": change, "amount": amount, "baseline": {"signal": base, "decision": decision(base)}}
    if change == "last_price_pct":
        alt = closes[:-1] + [closes[-1] * (1 + amount / 100)]
        s = ts_momentum.score(alt, m)
        note = (f"The model skips the last {m.skip_days} days, so a move in the latest close does not enter the signal"
                if m.skip_days and abs((s or 0) - base) < 1e-12 else "The latest close enters the trend window")
    elif change == "vol_multiplier":
        if amount <= 0:
            raise ValueError("vol multiplier must be positive")
        logs = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:])]
        mean = sum(logs) / len(logs)
        scaled = [mean + amount * (x - mean) for x in logs]
        alt = [closes[0]]
        for x in scaled:
            alt.append(alt[-1] * math.exp(x))
        s = ts_momentum.score(alt, m)
        note = "Daily moves around the same average drift are scaled. The signal divides by volatility"
    elif change == "spread_bps":
        limit = cfg.risk.hard_limits.max_spread_pct
        blocked = amount / 1e4 > limit
        out["hypothetical"] = {"signal": base, "decision": "BLOCKED BY RISK" if blocked else decision(base)}
        out["changed"] = blocked and decision(base) == "BUY"
        out["note"] = f"The risk service blocks a spread above {limit * 1e4:.0f} bps at order time"
        return out
    elif change == "remove_news":
        out["hypothetical"] = dict(out["baseline"])
        out["changed"] = False
        out["note"] = f"News is not an input to {ts_momentum.MODEL_ID} {ts_momentum.MODEL_VERSION}, so removing a story cannot change it"
        return out
    else:
        raise ValueError(f"unknown change {change}")
    out["hypothetical"] = {"signal": s, "decision": decision(s)}
    out["changed"] = decision(s) != decision(base)
    out["note"] = note
    return out


# Spaced review ---------------------------------------------------------------------------------

_REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_cards (
    card_id TEXT PRIMARY KEY, user TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT NOT NULL,
    prompt TEXT NOT NULL, answer TEXT NOT NULL, box INTEGER NOT NULL, due_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
"""


class Review:
    """Leitner boxes. A correct answer moves a card up one box, a wrong one sends it back to box 0."""

    def __init__(self, path: str | Path, intervals_days: tuple[int, ...], shared_across_threads: bool = False):
        self.intervals = intervals_days
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_REVIEW_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def _add(self, user: str, kind: str, source_id: str, prompt: str, answer: str, now: datetime) -> None:
        cid = make_id("card", {"user": user, "kind": kind, "source": source_id})
        self.conn.execute("INSERT OR IGNORE INTO review_cards VALUES (?,?,?,?,?,?,?,?,?)",
                          (cid, user, kind, source_id, prompt, answer, 0, to_micros(ensure_utc(now)), to_micros(ensure_utc(now))))

    def sync(self, user: str, predictions: list[dict], glossary: dict[str, dict], now: datetime,
             replay_clock: Optional[datetime] = None) -> None:
        """Add a card for each revealed wrong prediction and each glossary term."""
        for p in predictions:
            if p.get("outcome") is None:
                continue
            due = datetime.fromisoformat(p["made_at"]) + timedelta(days=p["horizon_days"])
            if p["context"] == "replay" and (replay_clock is None or due > ensure_utc(replay_clock)):
                continue  # not revealed yet
            stated, o = p["probability"], p["outcome"]
            if not ((o == 0 and stated > 0.5) or (o == 1 and stated < 0.5)):
                continue
            made = p["made_at"][:10]
            self._add(user, "wrong_prediction", p["prediction_id"],
                      f"On {made} you gave {p['symbol']} a {stated:.0%} chance of going {p['direction']} within {p['horizon_days']} days. "
                      "What happened, and what would you check first next time?",
                      f"It {'did' if o == 1 else 'did not'} go {p['direction']}. Compare the trend, recent news and the stated probability",
                      now)
        for key, e in glossary.items():
            self._add(user, "glossary", key, f"What is {e['plain'].lower()} ({key.replace('_', ' ')})?",
                      e["meaning"] + (f". Formula: {e['formula']}" if e.get("formula") else ""), now)

    def due(self, user: str, now: datetime, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            "SELECT card_id, kind, prompt, answer, box, due_at FROM review_cards WHERE user = ? AND due_at <= ? "
            "ORDER BY CASE kind WHEN 'wrong_prediction' THEN 0 ELSE 1 END, due_at LIMIT ?",
            (user, to_micros(ensure_utc(now)), limit))
        return [{"card_id": c, "kind": k, "prompt": p, "answer": a, "box": b, "due_at": from_micros(d).isoformat()}
                for c, k, p, a, b, d in cur.fetchall()]

    def answer(self, user: str, card_id: str, correct: bool, now: datetime) -> dict:
        rows = self.conn.execute("SELECT box FROM review_cards WHERE card_id = ? AND user = ?", (card_id, user)).fetchall()
        if not rows:
            raise KeyError(card_id)
        box = min(rows[0][0] + 1, len(self.intervals) - 1) if correct else 0
        due = ensure_utc(now) + timedelta(days=self.intervals[box])
        self.conn.execute("UPDATE review_cards SET box = ?, due_at = ? WHERE card_id = ?", (box, to_micros(due), card_id))
        return {"card_id": card_id, "box": box, "due_at": due.isoformat()}


# Crisis library --------------------------------------------------------------------------------

def crisis_library(store: PointInTimeStore, episodes: list, when: datetime) -> list[dict]:
    """Each episode is available only when stored closes, known by `when`, span its start and end."""
    try:
        rows = store.connection.execute(
            "SELECT min(event_time), max(event_time) FROM observations WHERE field = 'close' AND first_usable_at < ?",
            [to_micros(ensure_utc(when))]).fetchall()
    except Exception:
        rows = [(None, None)]
    lo, hi = rows[0] if rows else (None, None)
    lo_d = from_micros(lo).date() if lo is not None else None
    hi_d = from_micros(hi).date() if hi is not None else None
    out = []
    for e in episodes:
        covered = lo_d is not None and lo_d <= e.start and hi_d >= e.end
        out.append({"name": e.name, "start": e.start.isoformat(), "end": e.end.isoformat(),
                    "status": "AVAILABLE" if covered else "NOT AVAILABLE",
                    "reason": None if covered else (f"Stored price data covers {lo_d} to {hi_d}" if lo_d else "No stored price data"),
                    "what_current_rules_would_do": "NOT AVAILABLE. Needs the episode's data" if not covered
                    else "NOT AVAILABLE. Not computed yet. Replay the episode from its start date"})
    return out


# Concept map and daily lesson ------------------------------------------------------------------

def concept_order(prerequisites: dict[str, list[str]]) -> list[str]:
    """Every concept after its prerequisites, ties broken by name. Raises on a cycle."""
    done, order = set(), []
    remaining = dict(prerequisites)
    while remaining:
        ready = sorted(k for k, deps in remaining.items() if set(deps) <= done)
        if not ready:
            raise ValueError(f"prerequisite cycle among {sorted(remaining)}")
        for k in ready:
            order.append(k)
            done.add(k)
            del remaining[k]
    return order


def market_event(store: PointInTimeStore, master: InstrumentMaster, when: datetime) -> Optional[dict]:
    """The largest one-day move on the last recorded session known at `when`, with its source.
    Only names with a close on that session count, so a delisted name's old move never appears."""
    view = store.as_of(when)
    series = {i["instrument_id"]: view.series(i["instrument_id"], "close") for i in master.instruments()}
    last_day = max((s[-1].event_time.date() for s in series.values() if s), default=None)
    best = None
    for iid, s in series.items():
        if len(s) < 22 or s[-1].event_time.date() != last_day:
            continue
        a, b = s[-2], s[-1]
        if a.value and a.value > 0:
            r = b.value / a.value - 1
            rets = [y.value / x.value - 1 for x, y in zip(s[-22:-1], s[-21:]) if x.value]
            vol = (sum((x - sum(rets) / len(rets)) ** 2 for x in rets) / (len(rets) - 1)) ** 0.5 if len(rets) > 1 else None
            if best is None or abs(r) > abs(best["move"]):
                syms = master.symbols(iid)
                best = {"symbol": syms[-1] if syms else iid, "date": b.event_time.date().isoformat(),
                        "move": r, "vol20_daily": vol, "close": b.value, "vendor": b.vendor,
                        "known_from": b.first_usable_at.isoformat()}
    return best


def daily_lesson(glossary: dict, store: PointInTimeStore, master: InstrumentMaster, when: datetime) -> dict:
    """One concept a day in prerequisite order, illustrated with a recorded market event."""
    order = concept_order(glossary["prerequisites"])
    day = ensure_utc(when).date()
    concept = order[day.toordinal() % len(order)]
    term = glossary["terms"][concept]
    ev = market_event(store, master, when)
    lesson = {"date": day.isoformat(), "concept": concept, "plain": term["plain"], "meaning": term["meaning"],
              "formula": term.get("formula"), "typical": term.get("typical"),
              "prerequisites": [glossary["terms"][p]["plain"] for p in glossary["prerequisites"][concept]], "position": order.index(concept) + 1, "of": len(order),
              "event": ev}
    if ev is None:
        lesson["example"] = "NOT AVAILABLE. No recorded session with enough history yet"
    elif concept == "daily_return":
        lesson["example"] = f"{ev['symbol']} closed at {ev['close']:.2f} on {ev['date']}, a daily return of {ev['move'] * 100:+.2f}%"
    elif concept in ("volatility", "standard_error") and ev["vol20_daily"]:
        z = ev["move"] / ev["vol20_daily"]
        lesson["example"] = (f"{ev['symbol']} moved {ev['move'] * 100:+.2f}% on {ev['date']}. Its 20-day daily volatility was "
                             f"{ev['vol20_daily'] * 100:.2f}%, so the move was {z:+.1f} standard deviations")
    else:
        lesson["example"] = f"Largest recorded move on {ev['date']}: {ev['symbol']} {ev['move'] * 100:+.2f}%"
    return lesson
