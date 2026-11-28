"""Forex: pips, spreads from bid and ask candles, risk checks and a simulator.

Prices are a broker's own (OANDA practice), not the whole decentralized market. The simulator
fills at the bid or ask the broker showed. Overnight financing is not modeled and every
result says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Optional, Sequence

from ..core.config import ForexConfig
from .options import Check
from .store import Bar

SIM_LABEL = "Simulated at OANDA practice bid and ask. Overnight financing is not included. No broker order was sent"


class ConversionError(LookupError):
    pass


def split_pair(instrument: str) -> tuple[str, str]:
    base, quote = instrument.split("_")
    return base, quote


def pip_size(pip_location: int) -> float:
    """OANDA gives pipLocation, the power of ten of one pip (-4 for EUR_USD, -2 for USD_JPY)."""
    return 10.0 ** pip_location


def spread_pips(bid: float, ask: float, pip: float) -> float:
    return (ask - bid) / pip


@dataclass(frozen=True)
class SpreadModel:
    instrument: str
    observations: int
    median_pips: float
    p90_pips: float


def spread_model(instrument: str, bars: Sequence[Bar], pip: float) -> Optional[SpreadModel]:
    """Spread at each candle close, from the bid and ask candles. None without bid and ask data."""
    s = sorted(spread_pips(b.bid_close, b.ask_close, pip) for b in bars if b.bid_close is not None and b.ask_close is not None)
    if not s:
        return None
    return SpreadModel(instrument, len(s), median(s), s[min(len(s) - 1, int(0.9 * len(s)))])


def usd_per_quote(instrument: str, mid: float, mids: dict[str, float]) -> float:
    """USD value of one unit of the quote currency."""
    _, quote = split_pair(instrument)
    if quote == "USD":
        return 1.0
    if f"USD_{quote}" in mids:
        return 1.0 / mids[f"USD_{quote}"]
    if f"{quote}_USD" in mids:
        return mids[f"{quote}_USD"]
    if instrument == f"USD_{quote}":
        return 1.0 / mid
    raise ConversionError(f"no rate to convert {quote} to USD")


def notional_usd(instrument: str, units: float, mid: float, mids: dict[str, float]) -> float:
    base, _ = split_pair(instrument)
    if base == "USD":
        return abs(units)
    return abs(units) * mid * usd_per_quote(instrument, mid, mids)


def check_order(instrument: str, units: float, bid: float, ask: float, pip: float, equity: float, gross_open_usd: float,
                mids: dict[str, float], cfg: ForexConfig) -> list[Check]:
    r = cfg.risk
    mid = (bid + ask) / 2
    out = [Check("listed", instrument in cfg.instruments, f"{instrument} is {'on' if instrument in cfg.instruments else 'not on'} the research list")]
    sp = spread_pips(bid, ask, pip)
    out.append(Check("spread", sp <= r.max_spread_pips, f"Spread {sp:.1f} pips, at most {r.max_spread_pips:g} allowed"))
    try:
        n = notional_usd(instrument, units, mid, mids)
    except ConversionError as exc:
        return out + [Check("conversion", False, str(exc))]
    cap = r.max_notional_pct_equity * equity
    out.append(Check("position", n <= cap, f"Position {n:,.0f} USD, at most {cap:,.0f} USD ({r.max_notional_pct_equity:.0%} of the account)"))
    lev = (gross_open_usd + n) / equity if equity > 0 else float("inf")
    out.append(Check("leverage", lev <= r.max_gross_leverage + 1e-9,
                     f"All positions would be {lev:.2f} times the account, at most {r.max_gross_leverage:g}. Nothing is borrowed to trade"))
    return out


@dataclass(frozen=True)
class FxFill:
    instrument: str
    units: float
    price: float
    time: datetime
    label: str = SIM_LABEL


@dataclass
class ForexSimulator:
    cfg: ForexConfig
    cash_usd: float
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)  # units, average price
    fills: list = field(default_factory=list)

    def gross_usd(self, mids: dict[str, float]) -> float:
        return sum(notional_usd(i, u, mids[i], mids) for i, (u, _) in self.positions.items() if u)

    def unrealized_usd(self, mids: dict[str, float]) -> float:
        total = 0.0
        for i, (u, avg) in self.positions.items():
            total += u * (mids[i] - avg) * usd_per_quote(i, mids[i], mids)
        return total

    def equity(self, mids: dict[str, float]) -> float:
        return self.cash_usd + self.unrealized_usd(mids)

    def order(self, instrument: str, units: float, bid: float, ask: float, pip: float, now: datetime,
              mids: dict[str, float]) -> tuple[str, list[Check], Optional[FxFill]]:
        eq = self.equity(mids)
        held, avg = self.positions.get(instrument, (0.0, 0.0))
        reducing = held and (held > 0) != (units > 0) and abs(units) <= abs(held)
        gross_other = self.gross_usd(mids) - (notional_usd(instrument, held, mids[instrument], mids) if held else 0.0)
        new_units = held + units
        checks = check_order(instrument, new_units, bid, ask, pip, eq, gross_other, mids, self.cfg)
        if not reducing and not all(c.passed for c in checks):
            return "blocked", checks, None
        price = ask if units > 0 else bid
        if held and (held > 0) != (units > 0):
            # Close against the existing position first, realizing its profit or loss.
            closed = min(abs(units), abs(held)) * (1 if held > 0 else -1)
            self.cash_usd += closed * (price - avg) * usd_per_quote(instrument, price, mids)
            if new_units and (new_units > 0) != (held > 0):
                avg = price  # flipped: the remainder opens at this price
        elif new_units:
            avg = (held * avg + units * price) / new_units
        if new_units:
            self.positions[instrument] = (new_units, avg)
        else:
            self.positions.pop(instrument, None)
        fill = FxFill(instrument, units, price, now)
        self.fills.append(fill)
        return "filled", checks, fill
