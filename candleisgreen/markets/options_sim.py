"""Options simulator inside the platform. No broker is involved.

Fills use the quote side a real order would meet (buy at the ask, sell at the bid). With the
free indicative feed those prices are not executable, so every fill and result carries that
label and `executable=False`. Nothing here can build or send a broker order: the order builder
in options.py refuses indicative quotes.

Assumptions, stated on every result:
- A multi-leg order fills as one package or not at all, at each leg's own quote side, and only
  when the net price is within the order's net limit. Real multi-leg fills can be better or worse,
  can fill partly over time, or not fill. Partial fills are not modeled.
- Expiry follows Alpaca's rules: exercise or assignment in the money by the threshold, worthless otherwise.
- Early assignment can be applied with `assign_early`. It is not predicted: dividend dates are not recorded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Sequence

from ..core.config import OptionsConfig
from .options import Check, ExpiryEvent, Leg, OptionContract, OptionQuote, check_strategy, passed, settle_at_expiry

INDICATIVE_LABEL = "Simulated at an indicative quote. Not an executable price, so results do not show real execution"
PACKAGE_LABEL = "All legs filled together at their own quote sides, within the net limit. A real multi-leg order could fill better, worse, partly or not at all"


@dataclass
class Position:
    contract: OptionContract
    quantity: int
    avg_premium: float


@dataclass(frozen=True)
class Fill:
    symbol: str
    quantity: int
    price: float
    side: str
    time: datetime
    label: str
    executable: bool = False


@dataclass(frozen=True)
class OrderResult:
    status: str  # filled or blocked
    checks: tuple[Check, ...]
    fills: tuple[Fill, ...] = ()


@dataclass
class OptionsSimulator:
    cfg: OptionsConfig
    cash: float
    shares: dict[str, int] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)
    history: list = field(default_factory=list)

    def premium_open(self) -> float:
        return sum(p.quantity * p.contract.multiplier * p.avg_premium for p in self.positions.values() if p.quantity > 0)

    def mark(self, quotes: dict[str, OptionQuote], spots: dict[str, float]) -> Optional[float]:
        """Account value at quote midpoints. None when any held contract has no midpoint."""
        total = self.cash + sum(q * spots.get(sym, 0.0) for sym, q in self.shares.items())
        for p in self.positions.values():
            q = quotes.get(p.contract.symbol)
            if q is None or q.mid is None:
                return None
            total += p.quantity * p.contract.multiplier * q.mid
        return total

    def open(self, orders: Sequence[tuple[OptionContract, int]], quotes: dict[str, OptionQuote], now: datetime,
             equity: float, net_limit: Optional[float] = None) -> OrderResult:
        """Open a position. `net_limit` is per share for the whole package: positive is the most you will pay,
        negative is the least credit you will take. Multi-leg orders need one, as at the broker."""
        legs: list[Leg] = []
        fills: list[Fill] = []
        for contract, qty in orders:
            q = quotes.get(contract.symbol)
            price = None if q is None else (q.ask if qty > 0 else q.bid)
            legs.append(Leg(contract, qty, price if price is not None else 0.0))
            if price is not None:
                exe = bool(q.executable)  # type: ignore[union-attr]
                label = "Simulated at the quoted price" if exe else INDICATIVE_LABEL
                if len(orders) > 1:
                    label = f"{label}. {PACKAGE_LABEL}"
                fills.append(Fill(contract.symbol, qty, price, "buy" if qty > 0 else "sell", now, label, exe))
        underlyings = {c.underlying for c, _ in orders}
        held = sum(self.shares.get(u, 0) for u in underlyings) if len(underlyings) == 1 else 0
        checks = list(check_strategy(legs, quotes, self.cfg, equity, self.cash, now, shares_held=held, premium_open=self.premium_open()))
        if len(orders) > 1:
            g = 0
            for _, qty in orders:
                g = math.gcd(g, abs(qty))
            net = sum(l.quantity * l.premium for l in legs) / g
            if net_limit is None:
                checks.append(Check("net_limit", False, "A multi-leg order needs a net limit price, as at the broker"))
            else:
                ok = net <= net_limit + 1e-9
                checks.append(Check("net_limit", ok, f"Net price {net:+.2f} per share at the quotes, limit {net_limit:+.2f}"
                                    + ("" if ok else ". Not filled")))
        if not passed(checks):
            return OrderResult("blocked", tuple(checks))
        for leg in legs:
            c = leg.contract
            self.cash -= leg.quantity * c.multiplier * leg.premium
            pos = self.positions.get(c.symbol)
            if pos is None:
                self.positions[c.symbol] = Position(c, leg.quantity, leg.premium)
            else:
                new_qty = pos.quantity + leg.quantity
                if new_qty == 0:
                    del self.positions[c.symbol]
                else:
                    if (pos.quantity > 0) == (leg.quantity > 0):
                        pos.avg_premium = (pos.avg_premium * pos.quantity + leg.premium * leg.quantity) / new_qty
                    pos.quantity = new_qty
        self.history.extend(fills)
        return OrderResult("filled", tuple(checks), tuple(fills))

    def assign_early(self, symbol: str, contracts: int, day: date) -> ExpiryEvent:
        """Apply an early assignment of `contracts` short contracts. Shares and cash move at the strike, as at expiry."""
        pos = self.positions.get(symbol)
        if pos is None or pos.quantity >= 0 or contracts <= 0 or contracts > -pos.quantity:
            raise ValueError(f"no short position of {contracts} contracts in {symbol} to assign")
        c = pos.contract
        shares = contracts * c.multiplier
        sign = 1 if c.kind == "put" else -1  # assigned put: buy shares. Assigned call: deliver shares
        ev = ExpiryEvent(symbol, "assignment", -contracts, sign * shares, -sign * shares * c.strike)
        self.shares[c.underlying] = self.shares.get(c.underlying, 0) + ev.share_change
        self.cash += ev.cash_change
        pos.quantity += contracts
        if pos.quantity == 0:
            del self.positions[symbol]
        self.history.append((day, ev))
        return ev

    def expire(self, day: date, closes: dict[str, float]) -> list[ExpiryEvent]:
        """Settle every contract expiring on `day`. A missing underlying close leaves the position open
        and is reported, because settling it would need an invented price."""
        events = []
        for sym, pos in list(self.positions.items()):
            if pos.contract.expiry != day:
                continue
            close = closes.get(pos.contract.underlying)
            if close is None:
                continue
            ev = settle_at_expiry(pos.contract, pos.quantity, close, self.cfg.auto_exercise_threshold_usd)
            self.shares[pos.contract.underlying] = self.shares.get(pos.contract.underlying, 0) + ev.share_change
            self.cash += ev.cash_change
            del self.positions[sym]
            events.append(ev)
        self.history.extend(events)
        return events

    def unsettled(self, day: date, closes: dict[str, float]) -> list[str]:
        return [s for s, p in self.positions.items() if p.contract.expiry <= day and p.contract.underlying not in closes]
