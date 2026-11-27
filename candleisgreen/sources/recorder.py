"""Survivorship-aware forward recorder (spec Phase 1, decisions Q1 and Q13).

`record_session` collects one session after the close: the full asset list including
inactive assets, unadjusted daily consolidated bars, corporate actions, and a completeness
flag. `backfill` collects a historical range and marks it `backfill`, with no asset-list
snapshot for past days, because none was taken then. Running either twice with the same
inputs stores the same result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..core.config import AppConfig
from ..core.schemas import CollectionMode, Observation
from ..core.timeutil import ensure_utc
from ..data.instruments import CompletenessRecord, InstrumentMaster
from ..data.pit_store import PointInTimeStore
from .alpaca import MARKET_TZ, AlpacaData, session_close_utc

BAR_FIELDS = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap", "n": "trade_count"}
SOURCE = "alpaca"
SYNTHETIC_VENDOR = "alpaca_synthetic"
LICENSE = "alpaca_market_data"


@dataclass(frozen=True)
class RecordResult:
    session_dates: tuple[date, ...]
    observations_added: int
    actions_added: int
    completeness_added: int
    missing_symbols: tuple[str, ...]


def _bar_date(bar: dict) -> date:
    t = ensure_utc(datetime.fromisoformat(bar["t"].replace("Z", "+00:00")))
    return t.astimezone(ZoneInfo(MARKET_TZ)).date()


def bars_to_observations(symbol: str, instrument_id: str, exchange: str, bars: list[dict], now: datetime,
                         mode: CollectionMode, cfg: AppConfig, synthetic: bool = False) -> list[Observation]:
    delay = timedelta(minutes=cfg.sources.alpaca.sip_delay_minutes)
    out = []
    for bar in bars:
        day = _bar_date(bar)
        close = session_close_utc(day, cfg.sources.recorder.close_time_local)
        available = close + delay
        usable = max(available, ensure_utc(now)) if mode is CollectionMode.LIVE else available
        for key, field in BAR_FIELDS.items():
            if key not in bar:
                continue
            value = bar[key]
            out.append(Observation(
                instrument_id=instrument_id, vendor=SYNTHETIC_VENDOR if synthetic else SOURCE, raw_symbol=symbol,
                exchange=exchange, field=field,
                value=None if value is None else float(value), event_time=close, published_at=close,
                vendor_available_at=available, ingested_at=ensure_utc(now), first_usable_at=usable,
                timezone=MARKET_TZ, currency="USD", adjustment_method="none", vintage=0,
                missing_flag=value is None, license="synthetic" if synthetic else LICENSE, collection_mode=mode))
    return out


def _snapshot(data: AlpacaData, master: InstrumentMaster, now: datetime) -> tuple[dict[str, str], dict[str, str], list[str]]:
    active = data.assets("active")
    inactive = data.assets("inactive")
    mapping = master.apply_snapshot(active + inactive, now)
    exchanges = {a["symbol"]: a.get("exchange", "") for a in active + inactive}
    return mapping, exchanges, [a["symbol"] for a in active]


def record_session(session_date: date, data: AlpacaData, store: PointInTimeStore, master: InstrumentMaster,
                   now: datetime, cfg: AppConfig) -> RecordResult:
    now = ensure_utc(now)
    mapping, exchanges, active_symbols = _snapshot(data, master, now)
    bars = data.daily_bars(active_symbols, session_date, session_date, now)
    local_now = now.astimezone(ZoneInfo(MARKET_TZ)).date()
    mode = CollectionMode.LIVE if local_now == session_date else CollectionMode.BACKFILL
    obs = []
    for symbol, rows in bars.items():
        iid = mapping.get(symbol) or master.instrument_for_symbol(symbol)
        if iid is None:
            continue
        obs += bars_to_observations(symbol, iid, exchanges.get(symbol, ""), rows, now, mode, cfg, data.synthetic)
    added = store.add(obs)
    actions = master.add_actions(data.corporate_actions(list(mapping), session_date, session_date), now)
    received = sorted(s for s, rows in bars.items() if rows)
    missing = tuple(sorted(set(active_symbols) - set(received)))
    rec = CompletenessRecord(
        session_date=session_date, source=SOURCE, session_open=bool(received), asset_list_snapshot_taken=True,
        snapshot_taken_at=now, symbols_expected=len(active_symbols), bars_received=len(received),
        missing_symbols=missing if received else (), collection_mode=mode.value, collected_at=now)
    return RecordResult((session_date,), added, actions, int(master.add_completeness(rec)), rec.missing_symbols)


def backfill(start: date, end: date, data: AlpacaData, store: PointInTimeStore, master: InstrumentMaster,
             now: datetime, cfg: AppConfig) -> RecordResult:
    """Historical range. Inactive symbols are requested too, so delisted names keep their history."""
    now = ensure_utc(now)
    mapping, exchanges, active_symbols = _snapshot(data, master, now)
    symbols = sorted(mapping)
    bars = data.daily_bars(symbols, start, end, now)
    obs = []
    by_day: dict[date, set[str]] = {}
    for symbol, rows in bars.items():
        iid = mapping.get(symbol) or master.instrument_for_symbol(symbol)
        if iid is None:
            continue
        obs += bars_to_observations(symbol, iid, exchanges.get(symbol, ""), rows, now, CollectionMode.BACKFILL, cfg,
                                    data.synthetic)
        for row in rows:
            by_day.setdefault(_bar_date(row), set()).add(symbol)
    added = store.add(obs)
    actions = master.add_actions(data.corporate_actions(symbols, start, end), now)
    flags = 0
    for day in sorted(by_day):
        rec = CompletenessRecord(
            session_date=day, source=SOURCE, session_open=True, asset_list_snapshot_taken=False,
            snapshot_taken_at=None, symbols_expected=len(symbols), bars_received=len(by_day[day]),
            missing_symbols=(), collection_mode=CollectionMode.BACKFILL.value, collected_at=now)
        flags += int(master.add_completeness(rec))
    return RecordResult(tuple(sorted(by_day)), added, actions, flags, ())
