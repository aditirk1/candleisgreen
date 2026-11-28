"""Crypto: fees, order book quality, risk checks, research measures and a simulator.

Crypto trades every day of the year, so daily measures use calendar days. Alpaca allows no
short selling and no margin for crypto, and this module enforces the same: a sell can never
exceed what is held.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from ..core.config import CryptoConfig
from ..core.timeutil import ensure_utc, parse_rfc3339
from .options import Check
from .store import Bar

DAYS_PER_YEAR = 365  # Calendar fact: crypto venues trade every day.
SIM_LABEL = "Simulated against the order book at that moment. Fees from Alpaca's published schedule. No broker was involved"


def fee_bps(cfg: CryptoConfig, volume_30d_usd: float, maker: bool) -> float:
    tier = [t for t in cfg.fee_tiers if volume_30d_usd >= t[0]][-1]
    return tier[1] if maker else tier[2]


@dataclass(frozen=True)
class BookQuality:
    mid: float
    spread_bps: float
    bid_depth_usd: float   # within the allowed spread of the midpoint
    ask_depth_usd: float
    book_time: Optional[str]


def book_quality(book: dict, cfg: CryptoConfig) -> Optional[BookQuality]:
    bids, asks = book.get("b") or [], book.get("a") or []
    if not bids or not asks:
        return None
    best_bid, best_ask = float(bids[0]["p"]), float(asks[0]["p"])
    if best_ask <= best_bid:
        return None
    mid = (best_bid + best_ask) / 2
    band = cfg.risk.max_spread_bps / 1e4 * mid
    bd = sum(float(l["p"]) * float(l["s"]) for l in bids if float(l["p"]) >= mid - band)
    ad = sum(float(l["p"]) * float(l["s"]) for l in asks if float(l["p"]) <= mid + band)
    return BookQuality(mid, (best_ask - best_bid) / mid * 1e4, bd, ad, book.get("t"))


def walk_book(levels: Sequence[dict], notional: float) -> Optional[tuple[float, float]]:
    """Average price and quantity to spend `notional` USD against the levels. None if the book is too thin."""
    left, qty, cost = notional, 0.0, 0.0
    for l in levels:
        p, s = float(l["p"]), float(l["s"])
        take = min(s, left / p)
        qty += take
        cost += take * p
        left -= take * p
        if left <= 1e-9:
            return cost / qty, qty
    return None


def check_freshness(quality: Optional[BookQuality], now: datetime, cfg: CryptoConfig) -> Check:
    """The book must carry a time, be no older than the limit and not be stamped in the future."""
    r = cfg.risk
    if quality is None or not quality.book_time:
        return Check("book_time", False, "The order book has no timestamp, so its age is unknown")
    try:
        t = parse_rfc3339(quality.book_time)
    except ValueError:
        return Check("book_time", False, f"The order book timestamp '{quality.book_time}' cannot be read")
    age = (ensure_utc(now) - t).total_seconds()
    if age < -r.max_clock_skew_seconds:
        return Check("book_time", False, f"The order book is stamped {-age:.1f} seconds in the future. Clocks disagree, so it is refused")
    return Check("book_time", age <= r.max_book_age_seconds,
                 f"Order book is {max(age, 0):.1f} seconds old, at most {r.max_book_age_seconds:g} seconds allowed")


def check_order(side: str, notional: float, symbol: str, quality: Optional[BookQuality], cfg: CryptoConfig, equity: float,
                held_value: float, total_crypto_value: float, now: Optional[datetime] = None) -> list[Check]:
    """Every check for one order. `now` is required for a fill: without it the book's age cannot be checked."""
    r = cfg.risk
    out = [Check("listed", symbol in cfg.symbols, f"{symbol} is {'on' if symbol in cfg.symbols else 'not on'} the research list")]
    out.append(Check("order_size", notional <= cfg.max_order_notional_usd,
                     f"Order {notional:,.0f} USD, Alpaca accepts at most {cfg.max_order_notional_usd:,.0f} USD per order"))
    if side == "sell":
        out.append(Check("no_short", notional <= held_value + 1e-6,
                         "Selling only what is held" if notional <= held_value + 1e-6 else "Crypto cannot be sold short. The sale is larger than the holding"))
    else:
        cap = r.max_position_pct_equity * equity
        out.append(Check("position", held_value + notional <= cap,
                         f"Position would be {held_value + notional:,.0f} USD, at most {cap:,.0f} USD ({r.max_position_pct_equity:.0%} of the account)"))
        cap2 = r.max_total_pct_equity * equity
        out.append(Check("total", total_crypto_value + notional <= cap2,
                         f"All crypto would be {total_crypto_value + notional:,.0f} USD, at most {cap2:,.0f} USD ({r.max_total_pct_equity:.0%} of the account)"))
    if quality is None:
        out.append(Check("book", False, "No usable order book"))
        return out
    out.append(check_freshness(quality, now, cfg) if now is not None else Check("book_time", False, "No decision time given, so the book's age cannot be checked"))
    out.append(Check("spread", quality.spread_bps <= r.max_spread_bps,
                     f"Spread {quality.spread_bps:.1f} bps, at most {r.max_spread_bps:g} bps allowed"))
    depth = quality.ask_depth_usd if side == "buy" else quality.bid_depth_usd
    need = max(r.min_book_depth_usd, notional)
    out.append(Check("depth", depth >= need, f"{depth:,.0f} USD on the book near the midpoint, {need:,.0f} USD needed"))
    return out


@dataclass(frozen=True)
class SeriesStats:
    days: int
    first: str
    last: str
    total_return: float
    annual_volatility: Optional[float]
    max_drawdown: float
    median_daily_volume: Optional[float]


def series_stats(bars: Sequence[Bar]) -> Optional[SeriesStats]:
    if len(bars) < 2:
        return None
    closes = [b.close for b in bars]
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    vol = None
    if len(rets) >= 20:
        tail = rets[-30:]
        m = sum(tail) / len(tail)
        vol = math.sqrt(sum((x - m) ** 2 for x in tail) / (len(tail) - 1)) * math.sqrt(DAYS_PER_YEAR)
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)
    vols = sorted(b.volume for b in bars[-30:] if b.volume is not None)
    return SeriesStats(len(bars), bars[0].start.date().isoformat(), bars[-1].start.date().isoformat(), closes[-1] / closes[0] - 1,
                       vol, mdd, vols[len(vols) // 2] if vols else None)


@dataclass(frozen=True)
class CryptoFill:
    symbol: str
    side: str
    quantity: float
    price: float
    fee_usd: float
    time: datetime
    label: str = SIM_LABEL


@dataclass
class CryptoSimulator:
    cfg: CryptoConfig
    cash: float
    holdings: dict[str, float] = field(default_factory=dict)
    volume_30d_usd: float = 0.0
    fills: list = field(default_factory=list)

    def value(self, mids: dict[str, float]) -> Optional[float]:
        total = self.cash
        for sym, q in self.holdings.items():
            if q and sym not in mids:
                return None
            total += q * mids.get(sym, 0.0)
        return total

    def order(self, side: str, symbol: str, notional: float, book: dict, now: datetime, equity: float,
              mids: dict[str, float]) -> tuple[str, list[Check], Optional[CryptoFill]]:
        quality = book_quality(book, self.cfg)
        held = self.holdings.get(symbol, 0.0) * (quality.mid if quality else 0.0)
        total = sum(q * mids.get(s, 0.0) for s, q in self.holdings.items())
        checks = check_order(side, notional, symbol, quality, self.cfg, equity, held, total, now)
        if side == "buy" and notional > self.cash:
            checks.append(Check("cash", False, f"Order {notional:,.0f} USD, cash {self.cash:,.0f} USD. Crypto cannot be bought on margin"))
        if not all(c.passed for c in checks):
            return "blocked", checks, None
        walked = walk_book(book["a"] if side == "buy" else book["b"], notional)
        if walked is None:
            checks.append(Check("depth", False, "The book is too thin to fill the order"))
            return "blocked", checks, None
        price, qty = walked
        fee = notional * fee_bps(self.cfg, self.volume_30d_usd, maker=False) / 1e4
        if side == "buy":
            self.cash -= notional
            self.holdings[symbol] = self.holdings.get(symbol, 0.0) + qty * (1 - fee / notional)
        else:
            self.holdings[symbol] = self.holdings.get(symbol, 0.0) - qty
            self.cash += notional - fee
        self.volume_30d_usd += notional
        fill = CryptoFill(symbol, side, qty, price, fee, now)
        self.fills.append(fill)
        return "filled", checks, fill
