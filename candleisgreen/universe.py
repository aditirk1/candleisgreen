"""Tradable universe U_t (spec C.1, decision Q5), from information usable at decision time.

Provisional filters: minimum price and 20-day median dollar volume, with lower exit levels
for names already held. Inactive, delisted, leveraged and inverse names are excluded.
Spread and halt checks happen at order time in the risk service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from .core.config import AppConfig
from .core.timeutil import ensure_utc, to_micros
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore


@dataclass(frozen=True)
class Member:
    instrument_id: str
    symbol: str
    last_close: float
    median_dollar_volume: float
    adv_shares: float


def status_at(master: InstrumentMaster, instrument_id: str, when: datetime) -> Optional[str]:
    rows = master.conn.execute(
        "SELECT status FROM status_history WHERE instrument_id = ? AND observed_at <= ? "
        "ORDER BY observed_at DESC, (status = 'delisted') DESC", [instrument_id, to_micros(ensure_utc(when))]).fetchall()
    return rows[0][0] if rows else None


def build(decision_time: datetime, store: PointInTimeStore, master: InstrumentMaster, cfg: AppConfig,
          held: frozenset = frozenset()) -> list[Member]:
    u = cfg.universe
    view = store.as_of(decision_time)
    out = []
    for inst in master.instruments():
        iid = inst["instrument_id"]
        if u.exclude_leveraged_inverse_etfs and inst["leveraged_or_inverse"]:
            continue
        status = status_at(master, iid, decision_time)
        if status not in (None, "active"):
            continue
        closes = view.series(iid, "close")
        volumes = view.series(iid, "volume")
        if len(closes) < u.dollar_volume_window_days or len(volumes) < u.dollar_volume_window_days:
            continue
        if (decision_time - closes[-1].event_time).days > 5:
            continue  # stale history, for example a name that stopped trading
        n = u.dollar_volume_window_days
        c = np.array([o.value for o in closes[-n:]], dtype=float)
        v = np.array([o.value for o in volumes[-n:]], dtype=float)
        mdv = float(np.median(c * v))
        price = float(c[-1])
        min_price, min_mdv = (u.exit_min_price, u.exit_min_median_dollar_volume_20d) if iid in held else (
            u.min_price, u.min_median_dollar_volume_20d)
        if price < min_price or mdv < min_mdv:
            continue
        out.append(Member(iid, closes[-1].raw_symbol, price, mdv, float(v.mean())))
    return out
