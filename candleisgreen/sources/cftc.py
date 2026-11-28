"""CFTC Commitments of Traders, futures only. Public domain (CFTC Web Policy).

Read from the CFTC Public Reporting Environment (Socrata). Checked live on 2026-11-28.
Datasets: legacy 6dca-aqww (from 1986), disaggregated 72hh-3qpy and TFF gpe5-46if (from 2006).

Timing: positions are as of Tuesday and published Friday at 15:30 ET. Holidays can delay a
release by one or two days. A report fetched within the conservative window counts from the
moment it was fetched. Older history counts from the conservative day (the following Monday,
15:30 ET), so no backtest can see a report before it was surely public.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from ..core.config import FuturesConfig
from ..core.timeutil import ensure_utc, local_to_utc

BASE = "https://publicreporting.cftc.gov"
DATASETS = {"legacy": "6dca-aqww", "disaggregated": "72hh-3qpy", "tff": "gpe5-46if"}
LICENSE = "cftc_public_domain"
VENDOR = "cftc"
MARKET_TZ = "America/New_York"

# Trader groups per report, as (label, long field, short field).
GROUPS = {
    "legacy": [("Non-commercial traders", "noncomm_positions_long_all", "noncomm_positions_short_all"),
               ("Commercial hedgers", "comm_positions_long_all", "comm_positions_short_all"),
               ("Small traders", "nonrept_positions_long_all", "nonrept_positions_short_all")],
    "disaggregated": [("Managed money", "m_money_positions_long_all", "m_money_positions_short_all"),
                      ("Producers and merchants", "prod_merc_positions_long", "prod_merc_positions_short"),
                      ("Swap dealers", "swap_positions_long_all", "swap__positions_short_all"),
                      ("Small traders", "nonrept_positions_long_all", "nonrept_positions_short_all")],
    "tff": [("Asset managers", "asset_mgr_positions_long", "asset_mgr_positions_short"),
            ("Leveraged funds", "lev_money_positions_long", "lev_money_positions_short"),
            ("Dealers", "dealer_positions_long_all", "dealer_positions_short_all"),
            ("Small traders", "nonrept_positions_long_all", "nonrept_positions_short_all")],
}


def report_date(row: dict) -> date:
    return date.fromisoformat(row["report_date_as_yyyy_mm_dd"][:10])


def first_usable_at(rep: date, ingested_at: datetime, cfg: FuturesConfig) -> datetime:
    conservative = local_to_utc(rep + timedelta(days=cfg.cot_conservative_usable_days), cfg.cot_release_time_local, MARKET_TZ)
    scheduled = local_to_utc(rep + timedelta(days=cfg.cot_release_weekday_offset_days), cfg.cot_release_time_local, MARKET_TZ)
    ing = ensure_utc(ingested_at)
    if ing < conservative:
        return max(ing, scheduled)
    return conservative


def fetch(transport, dataset: str, market_code: str, since: Optional[date] = None, limit: int = 1000) -> list[dict]:
    where = f"cftc_contract_market_code='{market_code}'" + (f" AND report_date_as_yyyy_mm_dd >= '{since.isoformat()}T00:00:00'" if since else "")
    return transport.get(BASE, f"/resource/{DATASETS[dataset]}.json",
                         {"$where": where, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": limit})


@dataclass(frozen=True)
class GroupNet:
    label: str
    long: int
    short: int
    net: int
    net_pct_oi: float


def positioning(row: dict, dataset: str) -> tuple[int, list[GroupNet]]:
    """Open interest and each trader group's long, short and net contracts in one report."""
    oi = int(float(row["open_interest_all"]))
    out = []
    for label, lf, sf in GROUPS[dataset]:
        lo, sh = int(float(row.get(lf) or 0)), int(float(row.get(sf) or 0))
        out.append(GroupNet(label, lo, sh, lo - sh, (lo - sh) / oi if oi else 0.0))
    return oi, out


def percentile(history: list[float], value: float) -> Optional[float]:
    """Share of the window at or below the latest value, 0 to 1. None with fewer than 26 reports."""
    if len(history) < 26:
        return None
    return sum(1 for v in history if v <= value) / len(history)
