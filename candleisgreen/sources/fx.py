"""FX rates from FRED (H.10 daily noon buying rates) and the local and FX split of returns.

Downloads use FRED's public CSV endpoint, which needs no key. A missing rate is never filled:
the valuation that needs it is NOT AVAILABLE (spec failure fixture "missing FX rate").
"""
from __future__ import annotations

import csv
import io
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Optional

# FRED series and how to turn them into USD per one unit of the foreign currency.
SERIES = {"EUR": ("DEXUSEU", False), "GBP": ("DEXUSUK", False), "JPY": ("DEXJPUS", True), "HKD": ("DEXHKUS", True)}
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


class MissingFxRateError(LookupError):
    pass


def parse_fred_csv(text: str) -> dict[date, float]:
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        key = [k for k in row if k != "observation_date"][0]
        if row[key] not in ("", "."):
            out[date.fromisoformat(row["observation_date"])] = float(row[key])
    return out


def fetch(series: str, timeout: float = 30) -> str:
    with urllib.request.urlopen(CSV_URL.format(series=series), timeout=timeout) as resp:
        return resp.read().decode("utf-8")


@dataclass
class FxTable:
    rates: dict[str, dict[date, float]]  # currency to date to FRED value

    def usd_per_unit(self, currency: str, day: date) -> float:
        if currency == "USD":
            return 1.0
        if currency not in SERIES or currency not in self.rates:
            raise MissingFxRateError(f"no FX series for {currency}")
        value = self.rates[currency].get(day)
        if value is None:
            raise MissingFxRateError(f"no {currency} rate on {day}")
        inverted = SERIES[currency][1]
        return 1.0 / value if inverted else value


@dataclass(frozen=True)
class FxSplit:
    local_return: float
    fx_return: float
    cross: float
    usd_return: float


def split(local_start: float, local_end: float, fx_start: float, fx_end: float) -> FxSplit:
    """USD return = (1 + local)(1 + fx) - 1, shown as local, FX and their cross term."""
    rl = local_end / local_start - 1
    rf = fx_end / fx_start - 1
    return FxSplit(rl, rf, rl * rf, (1 + rl) * (1 + rf) - 1)


def usd_split(table: FxTable, currency: str, local_start: float, local_end: float, start: date, end: date) -> Optional[FxSplit]:
    try:
        return split(local_start, local_end, table.usd_per_unit(currency, start), table.usd_per_unit(currency, end))
    except MissingFxRateError:
        return None
