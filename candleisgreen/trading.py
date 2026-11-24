"""Phase 1 trading loop: daily decision, then next-session execution. Simulation and paper only.

Decision (16:30 ET): universe from point-in-time data, Level A trend scores, sizing, and
proposals in the journal. Execution (next session, inside the configured window): each
proposal becomes a limit order priced from a fresh execution-grade quote, goes to the
separate risk service, and only an approved order reaches the broker adapter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Protocol

from . import universe
from .broker.base import BrokerAdapter
from .broker.reconcile import reconcile
from .core.config import AppConfig
from .core.licenses import load_licenses
from .core.schemas import OrderIntent, Quote, RiskContext, RiskVerdict, Side, Venue
from .core.timeutil import ensure_utc, in_local_window, local_to_utc
from .clusters import cluster_key
from .data.adjust import adjust_closes
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore
from .journal import Journal
from .models import ts_momentum
from .models.registry import ModelRegistry, assert_routing_allowed, load_models
from .pipeline import limit_price
from .risk.client import RiskClient

UNKNOWN_CLUSTER = "UNKNOWN"


@dataclass(frozen=True)
class MarketSnapshot:
    quote: Optional[Quote]
    market_open: Optional[bool]
    halted: Optional[bool]


class QuoteSource(Protocol):
    def snapshot(self, symbol: str, instrument_id: str, now: datetime) -> MarketSnapshot: ...


@dataclass
class FixedQuotes:
    """Quotes from a fixture or a test. A real source reads the free IEX real-time feed."""

    quotes: dict[str, Quote] = field(default_factory=dict)
    market_open: bool = True
    halted: frozenset = frozenset()

    def snapshot(self, symbol: str, instrument_id: str, now: datetime) -> MarketSnapshot:
        return MarketSnapshot(self.quotes.get(symbol), self.market_open, symbol in self.halted)


@dataclass(frozen=True)
class DecisionResult:
    decision_time: datetime
    forecasts: int
    proposal_ids: tuple[str, ...]
    equity: float


def _last_closes(store: PointInTimeStore, iids, when: datetime, with_vendor: bool = False) -> dict:
    view = store.as_of(when)
    out = {}
    for iid in iids:
        series = view.series(iid, "close")
        if series:
            out[iid] = (series[-1].value, series[-1].vendor) if with_vendor else series[-1].value
    return out


def _cluster_exposure(store, master, instrument_id, now, positions, pending, mark, mid):
    """Held and pending value in the order's cluster. None, which blocks the order, when the order's
    cluster or that of any held or pending name is unknown (decision Q7)."""
    keys = {i: cluster_key(store.connection, master, i, now)[0]
            for i in {instrument_id} | {i for i, q in positions.items() if q > 0} | set(pending)}
    if any(k is None for k in keys.values()):
        return None, None
    key = keys[instrument_id]
    held = sum(q * mark.get(i, 0.0) for i, q in positions.items() if q > 0 and keys[i] == key)
    waiting = sum(q * mark.get(i, mid) for i, q in pending.items() if keys[i] == key)
    return held, waiting


def run_decision(decision_date: date, session_date: date, store: PointInTimeStore, master: InstrumentMaster,
                 journal: Journal, cfg: AppConfig, now: datetime) -> DecisionResult:
    tz = cfg.time.market_timezone
    decision_time = local_to_utc(decision_date, cfg.time.decision_time_local, tz)
    target_start = local_to_utc(session_date, "09:30", tz)
    entry = load_models().get(ts_momentum.MODEL_ID)
    positions = journal.positions()
    members = universe.build(decision_time, store, master, cfg, frozenset(positions))
    prices = _last_closes(store, set(positions) | {m.instrument_id for m in members}, decision_time)
    equity = journal.cash() + sum(q * prices.get(i, 0.0) for i, q in positions.items())
    journal.record_equity(decision_time, equity)
    names = {m.instrument_id: m.symbol for m in members}
    vendors = _last_closes(store, prices, decision_time, with_vendor=True)
    for iid, price in prices.items():
        synthetic = vendors.get(iid, (None, ""))[1].endswith("synthetic")
        journal.record_mark(iid, names.get(iid) or (master.symbols(iid) or ["?"])[-1], price, decision_time,
                            "close, synthetic" if synthetic else "close, delayed consolidated")

    scored = []
    view = store.as_of(decision_time)
    for m in members:
        obs = view.series(m.instrument_id, "close")
        adj = adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(m.instrument_id), decision_date)
        fc = ts_momentum.issue_forecast(m.instrument_id, obs, [c for _, c in adj], decision_time, ensure_utc(now),
                                        target_start, cfg.models.ts_momentum, sorted({o.license for o in obs}))
        if fc is None:
            continue
        journal._log("forecast_issued", fc.forecast_id, fc, "system:decision", ensure_utc(now))
        scored.append((fc, m))

    chosen = sorted((x for x in scored if x[0].signal_strength > 0), key=lambda x: -x[0].signal_strength)
    chosen = chosen[: cfg.sizing.max_names]
    targets = {m.instrument_id: math.floor(cfg.sizing.target_weight_per_name * equity / m.last_close)
               for _, m in chosen}
    forecast_for = {m.instrument_id: (fc, m) for fc, m in scored}
    symbols = {m.instrument_id: m.symbol for m in members}
    pids = []
    for iid in sorted(set(targets) | set(positions)):
        want = targets.get(iid, 0)
        have = positions.get(iid, 0.0)
        diff = want - have
        price = prices.get(iid)
        if price is None or abs(diff) * price < cfg.sizing.min_trade_value_usd:
            continue
        fc, _ = forecast_for.get(iid, (None, None))
        pids.append(journal.add_proposal(
            decision_date=decision_date, session_date=session_date, instrument_id=iid,
            symbol=symbols.get(iid) or (master.symbols(iid) or ["?"])[-1], side="buy" if diff > 0 else "sell",
            quantity=float(abs(diff)), forecast_id=fc.forecast_id if fc else "exit_no_forecast",
            model_id=ts_momentum.MODEL_ID, model_version=ts_momentum.MODEL_VERSION,
            signal_strength=fc.signal_strength if fc else None, now=ensure_utc(now)))
    return DecisionResult(decision_time, len(scored), tuple(pids), equity)


@dataclass(frozen=True)
class ExecutionResult:
    submitted: tuple[str, ...]
    blocked: dict
    skipped: tuple[str, ...]


def expire_unapproved(journal: Journal, session_date: date, now: datetime) -> int:
    n = 0
    for p in journal.proposals(session_date, "proposed"):
        journal.set_status(p.proposal_id, "expired", "system:executor", now, "not approved before the window closed")
        n += 1
    return n


def execute_session(session_date: date, now: datetime, journal: Journal, quotes: QuoteSource, risk: RiskClient,
                    broker: BrokerAdapter, store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig,
                    venue: Venue = Venue.SIMULATION, models: Optional[ModelRegistry] = None) -> ExecutionResult:
    now = ensure_utc(now)
    auto = cfg.execution.mode in ("auto_simulation", "broker_paper_auto")
    registry = models or load_models()

    def check_account() -> bool:
        """Reconcile before the first order and after every order. A mismatch fails closed."""
        try:
            rec = reconcile(broker.positions(), journal.positions())
        except Exception as exc:
            journal.record_reconciliation(False, [f"broker query failed ({type(exc).__name__})"], "system:executor", now)
            return False
        journal.record_reconciliation(rec.matched, rec.mismatches, "system:executor", now)
        return rec.matched
    licenses = load_licenses()
    tz = cfg.time.market_timezone
    in_window = in_local_window(now, cfg.time.execution_window_start_local, cfg.time.execution_window_end_local, tz)
    decision_time = local_to_utc(session_date, "00:00", tz)  # history known before this session
    if auto:
        for p in journal.proposals(session_date, "proposed"):
            journal.approve(p.proposal_id, "system:auto_simulation", now)
    positions = journal.positions()
    account_ok = check_account()
    submitted, skipped, blocked = [], [], {}
    for p in journal.proposals(session_date, "approved"):
        snap = quotes.snapshot(p.symbol, p.instrument_id, now)
        entry = registry.get(p.model_id)
        try:
            assert_routing_allowed(entry, venue, cfg.composite.eligibility.capital_min_tier)
            licenses.assert_use(entry.data_licenses, "paper_trading")
        except Exception as exc:
            journal.set_status(p.proposal_id, "blocked", "system:executor", now, str(exc))
            blocked[p.proposal_id] = [str(exc)]
            continue
        if snap.quote is None:
            journal.set_status(p.proposal_id, "blocked", "system:executor", now, "no execution-grade quote")
            blocked[p.proposal_id] = ["no execution-grade quote"]
            continue
        side = Side(p.side)
        intent = OrderIntent(
            forecast_id=p.forecast_id, asset_id=p.instrument_id, side=side, quantity=p.quantity,
            limit_price=round(limit_price(side, snap.quote, cfg.execution.limit_offset_fraction), 4),
            strategy_id=p.model_id, strategy_version=p.model_version, session_date=session_date.isoformat(),
            venue=venue, rationale=(f"{p.model_id} signal strength {p.signal_strength}",
                                    f"Proposal {p.proposal_id}", f"{venue.value} order"))
        last = _last_closes(store, set(positions) | {p.instrument_id}, decision_time)
        mark = {iid: last.get(iid, 0.0) for iid in set(positions) | {p.instrument_id}}
        mark[p.instrument_id] = snap.quote.mid
        equity = journal.cash() + sum(q * mark.get(i, 0.0) for i, q in positions.items())
        hist = journal.equity_history()
        day_start = hist[-1][1] if hist else journal.cash()
        pending = journal.pending_buys()
        cluster_value, pending_cluster = _cluster_exposure(store, master, p.instrument_id, now, positions, pending,
                                                           mark, snap.quote.mid)
        vols = store.as_of(decision_time).series(p.instrument_id, "volume")[-cfg.universe.dollar_volume_window_days:]
        adv = sum(o.value for o in vols) / len(vols) if vols else None
        mapped = master.instrument_for_symbol(p.symbol) == p.instrument_id and \
            universe.status_at(master, p.instrument_id, now) in (None, "active")
        ctx = RiskContext(
            now=now, kill_switch_engaged=False, market_open=snap.market_open, market_halted=snap.halted,
            broker_connected=True, account_state_known=account_ok, instrument_mapping_certain=mapped, quote=snap.quote,
            equity=equity, day_start_equity=day_start, position_value=positions.get(p.instrument_id, 0.0) * snap.quote.mid,
            cluster_value=cluster_value, pending_position_value=pending.get(p.instrument_id, 0.0) * snap.quote.mid,
            pending_cluster_value=pending_cluster, adv20_shares=adv, in_execution_window=in_window,
            instrument_tag=master.tag(p.instrument_id, cfg.markets.us_exchanges))
        decision = risk.evaluate(intent, ctx)
        journal.record_risk(intent, decision, now)
        if decision.verdict is not RiskVerdict.APPROVED:
            journal.set_status(p.proposal_id, "blocked", "service:risk", now, "\n".join(decision.reasons)[:1000],
                               intent.client_order_id)
            blocked[p.proposal_id] = list(decision.reasons)
            continue
        ack = broker.submit(intent, decision, snap.quote)
        for fill in ack.fills:
            journal.record_fill(fill)
        journal.record_mark(p.instrument_id, p.symbol, snap.quote.mid, now, f"mid, {snap.quote.feed}")
        status = {"filled": "filled", "partially_filled": "partially_filled", "accepted": "resting",
                  "rejected": "broker_rejected", "unknown": "unknown"}[ack.status]
        journal.set_status(p.proposal_id, status, f"broker:{venue.value.lower()}", now, ack.message, intent.client_order_id)
        positions = journal.positions()
        submitted.append(p.proposal_id)
        account_ok = check_account() and ack.status != "unknown"
    return ExecutionResult(tuple(submitted), blocked, tuple(skipped))
