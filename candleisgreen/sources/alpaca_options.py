"""Alpaca options data, read only. Free plan, indicative feed, paper trading host for contract lists.

Endpoints and fields follow Alpaca's documentation as read on 2026-11-28:
- GET {trading}/v2/options/contracts: contract list. Numbers arrive as strings.
- GET {data}/v1beta1/options/snapshots/{underlying}: chain with latestQuote, latestTrade, greeks, impliedVolatility.
- GET {data}/v1beta1/options/bars: historical bars, available since February 2024.
They have not been checked against a live response, because no keys exist in the build
environment. `tests/test_live_sources.py` runs that check once APCA keys are set.

The feed is always named. Only `indicative` is allowed, because OPRA needs a paid plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from ..core.config import AlpacaSourceConfig, OptionsConfig
from ..core.timeutil import ensure_utc, iso_utc, parse_rfc3339
from ..markets.options import OptionContract, OptionQuote, parse_occ
from .alpaca import Transport

CONTRACTS_PATH = "/v2/options/contracts"
CHAIN_PATH = "/v1beta1/options/snapshots/{underlying}"
BARS_PATH = "/v1beta1/options/bars"
FREE_FEEDS = ("indicative",)


class SubscriptionRequiredError(RuntimeError):
    """The request would need a paid market data plan."""


class HistoryNotAvailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContractInfo:
    contract: OptionContract
    tradable: bool
    open_interest: Optional[int]
    open_interest_date: Optional[str]
    close_price: Optional[float]
    close_price_date: Optional[str]


def _f(x: Any) -> Optional[float]:
    return None if x in (None, "") else float(x)


def _t(x: Optional[str]) -> Optional[datetime]:
    return None if not x else parse_rfc3339(x)


def parse_contract(row: dict) -> ContractInfo:
    c = OptionContract(symbol=row["symbol"], underlying=row["underlying_symbol"], expiry=date.fromisoformat(row["expiration_date"]),
                       kind=row["type"], strike=float(row["strike_price"]), style=row.get("style", "american"),
                       multiplier=int(float(row.get("multiplier") or 100)))
    if parse_occ(c.symbol).strike != c.strike:
        raise ValueError(f"contract {c.symbol} strike does not match its symbol")
    oi = row.get("open_interest")
    return ContractInfo(c, bool(row.get("tradable")), None if oi in (None, "") else int(float(oi)), row.get("open_interest_date"),
                        _f(row.get("close_price")), row.get("close_price_date"))


def parse_snapshot(symbol: str, snap: dict, feed: str, open_interest: Optional[int] = None) -> OptionQuote:
    q = snap.get("latestQuote") or {}
    tr = snap.get("latestTrade") or {}
    g = snap.get("greeks")
    return OptionQuote(symbol=symbol, feed=feed, bid=_f(q.get("bp")), ask=_f(q.get("ap")), quote_time=_t(q.get("t")),
                       last=_f(tr.get("p")), implied_volatility=_f(snap.get("impliedVolatility")),
                       greeks={k: float(v) for k, v in g.items()} if g else None, open_interest=open_interest)


class AlpacaOptions:
    def __init__(self, transport: Transport, alpaca: AlpacaSourceConfig, cfg: OptionsConfig):
        if cfg.feed not in FREE_FEEDS:
            raise SubscriptionRequiredError(f"feed '{cfg.feed}' needs a paid Alpaca plan. Only {FREE_FEEDS} is allowed")
        self.t, self.alpaca, self.cfg = transport, alpaca, cfg

    def contracts(self, underlying: str, expiry_from: date, expiry_to: date, kind: Optional[str] = None,
                  strike_min: Optional[float] = None, strike_max: Optional[float] = None) -> list[ContractInfo]:
        out: list[ContractInfo] = []
        token = None
        while True:
            params = {"underlying_symbols": underlying.upper(), "status": "active", "expiration_date_gte": expiry_from.isoformat(),
                      "expiration_date_lte": expiry_to.isoformat(), "type": kind, "strike_price_gte": strike_min,
                      "strike_price_lte": strike_max, "limit": 1000, "page_token": token}
            page = self.t.get(self.alpaca.trading_base_url, CONTRACTS_PATH, params)
            out.extend(parse_contract(r) for r in page.get("option_contracts") or [])
            token = page.get("next_page_token")
            if not token:
                return out

    def chain(self, underlying: str, expiry_from: Optional[date] = None, expiry_to: Optional[date] = None,
              kind: Optional[str] = None, open_interest: Optional[dict[str, int]] = None) -> dict[str, OptionQuote]:
        out: dict[str, OptionQuote] = {}
        token = None
        while True:
            params = {"feed": self.cfg.feed, "limit": 1000, "type": kind, "page_token": token,
                      "expiration_date_gte": expiry_from.isoformat() if expiry_from else None,
                      "expiration_date_lte": expiry_to.isoformat() if expiry_to else None}
            page = self.t.get(self.alpaca.data_base_url, CHAIN_PATH.format(underlying=underlying.upper()), params)
            for sym, snap in (page.get("snapshots") or {}).items():
                out[sym] = parse_snapshot(sym, snap, self.cfg.feed, (open_interest or {}).get(sym))
            token = page.get("next_page_token")
            if not token:
                return out

    def bars(self, symbols: Iterable[str], start: date, end: datetime, now: datetime, timeframe: str = "1Day") -> dict[str, list[dict]]:
        if start < self.cfg.history_start:
            raise HistoryNotAvailableError(f"options history starts {self.cfg.history_start}")
        latest = ensure_utc(now) - timedelta(minutes=self.cfg.history_end_delay_minutes)
        if ensure_utc(end) > latest:
            raise HistoryNotAvailableError(f"the free plan serves history ending at least {self.cfg.history_end_delay_minutes} minutes ago")
        syms = sorted(set(symbols))
        out: dict[str, list[dict]] = {}
        for i in range(0, len(syms), 100):
            token = None
            while True:
                params = {"symbols": ",".join(syms[i:i + 100]), "timeframe": timeframe, "start": start.isoformat(),
                          "end": iso_utc(ensure_utc(end)), "limit": 10000, "page_token": token}
                page = self.t.get(self.alpaca.data_base_url, BARS_PATH, params)
                for sym, rows in (page.get("bars") or {}).items():
                    out.setdefault(sym, []).extend(rows)
                token = page.get("next_page_token")
                if not token:
                    break
        return out
