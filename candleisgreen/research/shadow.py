"""Tier 5 shadow tracking (spec decision Q8 and the governance rules).

A strategy at Tier 4 shadows as soon as its implementation is ready. Each day it records target
weights before the session they apply to, so the record is prospective by construction. A target
recorded after its session started is stored as retrospective and makes the whole record ineligible.

At registration the expected annual return and its standard error are frozen. The acceptance band
is fixed by formula at that moment: expected return plus or minus z times the combined standard
error of the frozen estimate and the shadow period's own sampling error, with z from
`composite.promotion.shadow_band_level`.

Each later close marks the book: gross return of the held weights, modeled costs from turnover,
and net return. `record()` builds the `ShadowRecord` that `promotion_check` reads. A pass opens a
promotion proposal to Tier 5, which only Aditi can decide. Nothing here places an order.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from scipy.stats import norm

from ..composite.eligibility import ShadowRecord, StrategyPromotionPolicy, promotion_check
from ..core.config import AppConfig
from ..core.sqlite_shared import connect as sqlite_connect
from ..core.timeutil import ensure_utc, iso_utc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_registrations (
    strategy_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, expected_mean_annual REAL NOT NULL,
    expected_se_annual REAL NOT NULL, band_level REAL NOT NULL, policy_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_targets (
    strategy_id TEXT NOT NULL, as_of TEXT NOT NULL, issued_at TEXT NOT NULL, target_start TEXT NOT NULL,
    weights_json TEXT NOT NULL, record_type TEXT NOT NULL, PRIMARY KEY (strategy_id, as_of)
);
CREATE TABLE IF NOT EXISTS shadow_returns (
    strategy_id TEXT NOT NULL, as_of TEXT NOT NULL, end_date TEXT NOT NULL, gross REAL NOT NULL, cost REAL NOT NULL,
    net REAL NOT NULL, turnover REAL NOT NULL, PRIMARY KEY (strategy_id, as_of)
);
"""


class ShadowBook:
    def __init__(self, path: str | Path, cfg: AppConfig, shared_across_threads: bool = False):
        self.cfg = cfg
        self.conn = sqlite_connect(path, shared_across_threads)
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # Registration and targets --------------------------------------------------------------

    def register(self, strategy_id: str, expected_mean_annual: float, expected_se_annual: float, now: datetime,
                 policy: Optional[StrategyPromotionPolicy] = None) -> bool:
        """Freeze the expectation. Returns False when the strategy is already registered."""
        policy = policy or StrategyPromotionPolicy()
        cur = self.conn.execute("INSERT OR IGNORE INTO shadow_registrations VALUES (?,?,?,?,?,?)",
                                (strategy_id, iso_utc(now), float(expected_mean_annual), float(expected_se_annual),
                                 self.cfg.composite.promotion.shadow_band_level,
                                 json.dumps({"min_trades": policy.min_trades,
                                             "max_se_to_expected_ratio": policy.max_se_to_expected_ratio})))
        return bool(cur.rowcount)

    def registered(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT strategy_id FROM shadow_registrations").fetchall()]

    def record_targets(self, strategy_id: str, as_of: datetime, issued_at: datetime, target_start: datetime,
                       weights: dict[str, float]) -> str:
        if strategy_id not in self.registered():
            raise ValueError(f"{strategy_id} is not registered for shadow tracking")
        kind = "prospective" if ensure_utc(issued_at) < ensure_utc(target_start) else "retrospective"
        clean = {k: float(v) for k, v in weights.items() if abs(v) > 0}
        self.conn.execute("INSERT OR IGNORE INTO shadow_targets VALUES (?,?,?,?,?,?)",
                          (strategy_id, iso_utc(as_of), iso_utc(issued_at), iso_utc(target_start),
                           json.dumps(clean, sort_keys=True), kind))
        return kind

    # Marking -------------------------------------------------------------------------------

    def mark(self, store, now: datetime) -> int:
        """Mark every target whose next close after its session start is known by `now`."""
        half_spread = self.cfg.research.default_half_spread
        done = 0
        view = store.as_of(ensure_utc(now))
        for sid in self.registered():
            rows = self.conn.execute(
                "SELECT as_of, target_start, weights_json FROM shadow_targets WHERE strategy_id = ? ORDER BY as_of",
                (sid,)).fetchall()
            marked = {r[0] for r in self.conn.execute("SELECT as_of FROM shadow_returns WHERE strategy_id = ?", (sid,)).fetchall()}
            prev: dict[str, float] = {}
            for as_of, start, wj in rows:
                w = json.loads(wj)
                turnover = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in set(w) | set(prev))
                prev = w
                if as_of in marked:
                    continue
                t0, t1 = datetime.fromisoformat(as_of), datetime.fromisoformat(start)
                gross, end_date, ok = 0.0, None, True
                for iid, wi in w.items():
                    s = view.series(iid, "close")
                    before = [o for o in s if o.event_time <= t0]
                    after = [o for o in s if o.event_time >= t1]
                    if not before or not after:
                        ok = False
                        break
                    gross += wi * (after[0].value / before[-1].value - 1)
                    end_date = max(end_date or after[0].event_time, after[0].event_time)
                if not ok or end_date is None:
                    continue
                cost = turnover * half_spread
                self.conn.execute("INSERT OR IGNORE INTO shadow_returns VALUES (?,?,?,?,?,?,?)",
                                  (sid, as_of, end_date.date().isoformat(), gross, cost, gross - cost, turnover))
                done += 1
        return done

    # Evaluation ----------------------------------------------------------------------------

    def record(self, strategy_id: str) -> Optional[ShadowRecord]:
        reg = self.conn.execute("SELECT expected_mean_annual, expected_se_annual, band_level FROM shadow_registrations "
                                "WHERE strategy_id = ?", (strategy_id,)).fetchall()
        if not reg:
            return None
        mean_pre, se_pre, level = reg[0]
        rets = self.conn.execute("SELECT gross, net, turnover FROM shadow_returns WHERE strategy_id = ? ORDER BY as_of",
                                 (strategy_id,)).fetchall()
        kinds = {r[0] for r in self.conn.execute("SELECT record_type FROM shadow_targets WHERE strategy_id = ?",
                                                 (strategy_id,)).fetchall()}
        days = self.cfg.composite.research_portfolio.trading_days_per_year
        n = len(rets)
        net = [r[1] for r in rets]
        mean_d = sum(net) / n if n else 0.0
        var_d = sum((x - mean_d) ** 2 for x in net) / (n - 1) if n > 1 else 0.0
        realized_mean = mean_d * days
        realized_se = math.sqrt(var_d * days) / math.sqrt(n / days) if n > 1 else float("inf")
        z = norm.ppf(0.5 + level / 2)
        half = z * math.sqrt(se_pre ** 2 + (realized_se ** 2 if math.isfinite(realized_se) else 0.0))
        diffs = [r[1] - r[0] for r in rets]
        md = sum(diffs) / n if n else 0.0
        te = math.sqrt(sum((d - md) ** 2 for d in diffs) / (n - 1) * days) if n > 1 else 0.0
        trades = sum(1 for r in rets if r[2] >= self.cfg.composite.promotion.shadow_min_turnover)
        return ShadowRecord(trading_days=n, trades=trades, expected_mean_annual=mean_pre,
                            realized_mean_annual=realized_mean, realized_se_annual=realized_se,
                            band_low_annual=mean_pre - half, band_high_annual=mean_pre + half,
                            tracking_error_annual=te, prospective=kinds <= {"prospective"})

    def evaluate(self, strategy_id: str, registry, now: datetime) -> dict:
        """Run the Tier 5 gate. A pass opens one promotion proposal for Aditi."""
        rec = self.record(strategy_id)
        if rec is None:
            return {"strategy_id": strategy_id, "status": "NOT REGISTERED"}
        pol = json.loads(self.conn.execute("SELECT policy_json FROM shadow_registrations WHERE strategy_id = ?",
                                           (strategy_id,)).fetchall()[0][0])
        result = promotion_check(rec, self.cfg.composite.promotion, StrategyPromotionPolicy(**pol))
        out = {"strategy_id": strategy_id, "record": rec.__dict__, "passed": result.eligible,
               "reasons": list(result.reasons), "proposal_id": None}
        if result.eligible:
            pending = [p for p in registry.promotions()
                       if p["signal_id"] == strategy_id and p["to_tier"] == 5 and p["status"] in ("PENDING", "APPROVED")]
            out["proposal_id"] = pending[0]["proposal_id"] if pending else registry.propose_promotion(
                strategy_id, 5, {"shadow": rec.__dict__, "check": "promotion_check passed"}, now)
        return out
