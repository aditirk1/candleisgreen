"""Experiment lab (spec Teaching): a trade idea in plain words becomes a null hypothesis, a data plan
and an out-of-sample test, then enters the same research pipeline as any paper.

The idea is parsed with the same fixed rules as the Research Capture Inbox, so nothing is inferred
beyond the words. Data the store holds is marked available, anything else is NEEDS DATA with the
free substitute the factory knows. The newest `research.lab_holdout_fraction` of history is
reserved for the out-of-sample test and must not be looked at while designing the rule.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from ..core.config import AppConfig
from ..data.instruments import InstrumentMaster
from ..data.pit_store import PointInTimeStore
from ..research import factory
from ..research.inbox import extract_claims


def design(idea: str, store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig, now: datetime) -> dict:
    text = idea.strip()
    if not text:
        raise ValueError("state the idea in words")
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cards = extract_claims(text if text.endswith((".", "!", "?")) else text + ".", h, now, None)
    if not cards:
        return {"status": "NEEDS INPUT", "request": "Say what should rise or fall, against what, and over how long. "
                "For example: stocks with rising 12-month returns earn higher returns over the next month."}
    card = {**cards[0], "source_type": "experiment_lab", "evidence_label": "opinion"}
    up = card["direction"] == "positive"
    horizon = card["horizon"] or "NOT STATED. A horizon must be fixed before the test runs"
    view = store.as_of(now)
    data, missing = [], []
    for sym in card["instruments"]:
        iid = master.instrument_for_symbol(sym)
        n = len(view.series(iid, "close")) if iid else 0
        (data if n else missing).append(f"{sym} daily closes ({n} sessions stored)" if n else f"{sym} daily closes")
    if not card["instruments"]:
        data.append("Daily closes for the recorded universe")
    card["data_required"] = missing
    holdout = cfg.research.lab_holdout_fraction
    plan = {
        "null_hypothesis": (f"The effect described has {'no positive' if up else 'no negative'} return over {horizon}. "
                            f"The true mean is {'at most' if up else 'at least'} zero."),
        "alternative": f"The mean return is {'above' if up else 'below'} zero",
        "data_available": data, "data_missing": [{"data": m, "free_substitute": factory.FREE_SUBSTITUTES.get(m.lower(), "none known")} for m in missing],
        "out_of_sample": (f"The newest {holdout:.0%} of history is held out. Design on the rest, then run once on the holdout. "
                          f"Pass rule: {factory.RULES[card['study_type']]}"),
        "study_type": card["study_type"], "claim_type": card["claim_type"],
    }
    return {"status": "DESIGNED", "card": card, "plan": plan}


def submit(designed: dict, registry, cfg: AppConfig, now: datetime) -> dict:
    """Run the designed idea through the factory, the same path as a paper. Returns the digest entry."""
    if designed.get("status") != "DESIGNED":
        raise ValueError("only a designed idea can be submitted")
    digest = factory.run_daily([designed["card"]], registry, factory.Library({}, {}), set(), cfg, now)
    for key in ("new_hypotheses", "needs_data", "duplicates"):
        if digest[key]:
            return {"outcome": key, **digest[key][0]}
    return {"outcome": "recorded"}
