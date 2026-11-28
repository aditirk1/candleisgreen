"""US equity options: contracts, payoffs, a theoretical pricing model, expiry and risk checks.

Rules this module keeps:
- A market price comes only from a quote with its feed named. Alpaca's free feed is
  "indicative", a modified derivative of OPRA quotes. It is never presented as executable.
- Black-Scholes values are theoretical. They are labeled as model output with their inputs
  and never stand in for a market price.
- A strategy with an unlimited possible loss is refused. Short calls must be covered by
  shares or a long call. Short puts must be covered by a long put or by cash.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional, Sequence
from zoneinfo import ZoneInfo

from ..core.config import OptionsConfig
from ..core.timeutil import ensure_utc, local_to_utc

Kind = Literal["call", "put"]
OCC_RE = re.compile(r"^([A-Z0-9.]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
MARKET_TZ = "America/New_York"


class OptionSymbolError(ValueError):
    pass


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    expiry: date
    kind: Kind
    strike: float
    style: str = "american"
    multiplier: int = 100

    def intrinsic(self, spot: float) -> float:
        return max(spot - self.strike, 0.0) if self.kind == "call" else max(self.strike - spot, 0.0)

    def days_to_expiry(self, today: date) -> int:
        return (self.expiry - today).days


def parse_occ(symbol: str, multiplier: int = 100, style: str = "american") -> OptionContract:
    """OCC symbology: root, YYMMDD, C or P, strike times 1000 in eight digits. AAPL250117C00150000."""
    m = OCC_RE.match(symbol.strip().upper())
    if not m:
        raise OptionSymbolError(f"'{symbol}' is not an OCC option symbol")
    root, yy, mm, dd, cp, strike = m.groups()
    return OptionContract(symbol=symbol.strip().upper(), underlying=root, expiry=date(2000 + int(yy), int(mm), int(dd)),
                          kind="call" if cp == "C" else "put", strike=int(strike) / 1000, style=style, multiplier=multiplier)


def format_occ(underlying: str, expiry: date, kind: Kind, strike: float) -> str:
    milli = round(strike * 1000)
    if strike <= 0 or abs(milli - strike * 1000) > 1e-6 or milli >= 10**8:
        raise OptionSymbolError(f"strike {strike} cannot be written in OCC form")
    return f"{underlying.upper()}{expiry:%y%m%d}{'C' if kind == 'call' else 'P'}{milli:08d}"


@dataclass(frozen=True)
class OptionQuote:
    """One contract's quote as a feed reported it. Prices are per share. The feed is always named."""
    symbol: str
    feed: str
    bid: Optional[float]
    ask: Optional[float]
    quote_time: Optional[datetime]
    last: Optional[float] = None
    implied_volatility: Optional[float] = None
    greeks: Optional[dict] = None
    open_interest: Optional[int] = None

    @property
    def mid(self) -> Optional[float]:
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask < self.bid:
            return None
        return (self.bid + self.ask) / 2

    @property
    def spread_pct_of_mid(self) -> Optional[float]:
        mid = self.mid
        return None if not mid else (self.ask - self.bid) / mid  # type: ignore[operator]

    @property
    def executable(self) -> bool:
        """Only a consolidated OPRA quote can be treated as executable. The indicative feed never is."""
        return self.feed == "opra"


@dataclass(frozen=True)
class Leg:
    """Quantity is in contracts: positive long, negative short. Premium is per share, paid when positive."""
    contract: OptionContract
    quantity: int
    premium: float

    def __post_init__(self):
        if int(self.quantity) != self.quantity or self.quantity == 0:
            raise ValueError("option quantity must be a whole, non-zero number of contracts")


@dataclass(frozen=True)
class StockLeg:
    """Shares held alongside the options, with their cost per share."""
    quantity: int
    cost: float


def leg_value_at_expiry(leg: Leg, spot: float) -> float:
    return leg.quantity * leg.contract.multiplier * (leg.contract.intrinsic(spot) - leg.premium)


def payoff_at_expiry(legs: Sequence[Leg], spot: float, stock: Optional[StockLeg] = None) -> float:
    """Profit or loss in USD if every leg is held to expiry and the underlying closes at `spot`."""
    total = sum(leg_value_at_expiry(l, spot) for l in legs)
    if stock:
        total += stock.quantity * (spot - stock.cost)
    return total


@dataclass(frozen=True)
class StrategyProfile:
    net_premium: float            # USD paid (positive) or received (negative) to open
    max_loss: Optional[float]     # USD, positive number. None means unlimited
    max_gain: Optional[float]     # USD. None means unlimited
    breakevens: tuple[float, ...]
    points: tuple[tuple[float, float], ...] = field(default=())


def profile(legs: Sequence[Leg], stock: Optional[StockLeg] = None, points: int = 0) -> StrategyProfile:
    """Exact profile of a piecewise linear payoff. Kinks sit at strikes, so the extremes are at a
    strike, at zero, or beyond the highest strike where the slope decides boundedness."""
    if not legs and not stock:
        raise ValueError("a strategy needs at least one leg")
    strikes = sorted({l.contract.strike for l in legs})
    top = (strikes[-1] if strikes else (stock.cost if stock else 1.0)) * 2 + 1
    xs = sorted({0.0, *strikes, top})
    f = lambda s: payoff_at_expiry(legs, s, stock)  # noqa: E731
    vals = [f(x) for x in xs]
    slope_up = (f(top + 1) - f(top))
    lo, hi = min(vals), max(vals)
    max_loss = None if slope_up < -1e-9 else max(0.0, -lo)
    max_gain = None if slope_up > 1e-9 else max(0.0, hi)
    bes = []
    for a, b, fa, fb in zip(xs, xs[1:], vals, vals[1:]):
        if fa == 0:
            bes.append(a)
        elif fa * fb < 0:
            bes.append(a + (b - a) * (-fa) / (fb - fa))
    if slope_up != 0 and vals[-1] * slope_up < 0:
        bes.append(top - vals[-1] / slope_up)
    pts: tuple[tuple[float, float], ...] = ()
    if points:
        # Chart range around the strikes, where the payoff changes shape.
        a, b = (strikes[0], strikes[-1]) if strikes else (top / 2, top / 2)
        half = max((b - a) * 1.5, (a + b) / 2 * 0.08)
        lo, hi = max(0.0, a - half), b + half
        step = (hi - lo) / points
        pts = tuple((round(lo + i * step, 4), round(f(lo + i * step), 2)) for i in range(points + 1))
    net = sum(l.quantity * l.contract.multiplier * l.premium for l in legs)
    return StrategyProfile(net_premium=net, max_loss=max_loss, max_gain=max_gain,
                           breakevens=tuple(sorted(round(b, 4) for b in set(bes))), points=pts)


# Theoretical value. Black-Scholes for a European option on a non-dividend stock. American calls
# on such a stock have the same value. American puts are worth at least this. Always labeled.
def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


@dataclass(frozen=True)
class ModelValue:
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_vol_point: float
    rho_per_rate_point: float
    inputs: dict
    label: str = "Theoretical value from the Black-Scholes model. Not a market price"


def black_scholes(kind: Kind, spot: float, strike: float, years: float, vol: float, rate: float) -> ModelValue:
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    inputs = {"spot": spot, "strike": strike, "years": years, "volatility": vol, "rate": rate, "model": "black_scholes"}
    if years <= 0 or vol <= 0:
        intrinsic = max(spot - strike, 0) if kind == "call" else max(strike - spot, 0)
        itm = intrinsic > 0
        return ModelValue(intrinsic, (1.0 if itm else 0.0) if kind == "call" else (-1.0 if itm else 0.0), 0, 0, 0, 0, inputs)
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2) * years) / sq
    d2 = d1 - sq
    disc = math.exp(-rate * years)
    if kind == "call":
        price = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
        delta = _ncdf(d1)
        theta = -spot * _npdf(d1) * vol / (2 * math.sqrt(years)) - rate * strike * disc * _ncdf(d2)
        rho = strike * years * disc * _ncdf(d2)
    else:
        price = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        delta = _ncdf(d1) - 1
        theta = -spot * _npdf(d1) * vol / (2 * math.sqrt(years)) + rate * strike * disc * _ncdf(-d2)
        rho = -strike * years * disc * _ncdf(-d2)
    gamma = _npdf(d1) / (spot * sq)
    vega = spot * _npdf(d1) * math.sqrt(years)
    return ModelValue(price, delta, gamma, theta / 365, vega / 100, rho / 100, inputs)


# Expiry. Alpaca exercises a long contract in the money by at least the threshold, and assigns
# a short one on the same rule. Everything else expires worthless.
@dataclass(frozen=True)
class ExpiryEvent:
    symbol: str
    action: Literal["exercise", "assignment", "expire"]
    contracts: int
    share_change: int      # shares bought (+) or sold (-)
    cash_change: float     # USD


def settle_at_expiry(contract: OptionContract, quantity: int, underlying_close: float, threshold: float) -> ExpiryEvent:
    itm_by = contract.intrinsic(underlying_close)
    shares = abs(quantity) * contract.multiplier
    if itm_by < threshold or itm_by == 0:
        return ExpiryEvent(contract.symbol, "expire", quantity, 0, 0.0)
    action: Literal["exercise", "assignment"] = "exercise" if quantity > 0 else "assignment"
    # Long call exercised or short put assigned: shares come in at the strike.
    receives_shares = (contract.kind == "call") == (quantity > 0)
    sign = 1 if receives_shares else -1
    return ExpiryEvent(contract.symbol, action, quantity, sign * shares, -sign * shares * contract.strike)


# Risk checks. Every check runs before a simulated order fills, and would run before any broker
# order. A failed check blocks. Each reason names the setting that decided it.
@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    reason: str


def _covered(legs: Sequence[Leg], shares_held: int, cash: float) -> list[Check]:
    out = []
    calls_short = sum(-l.quantity for l in legs if l.contract.kind == "call" and l.quantity < 0)
    calls_long = sum(l.quantity for l in legs if l.contract.kind == "call" and l.quantity > 0)
    by_shares = shares_held // 100
    uncovered_calls = max(0, calls_short - calls_long - by_shares)
    out.append(Check("short_calls_covered", uncovered_calls == 0,
                     "Every short call is covered by shares or a long call" if uncovered_calls == 0
                     else f"{uncovered_calls} short call contracts are uncovered, so the possible loss has no limit"))
    puts_short = [l for l in legs if l.contract.kind == "put" and l.quantity < 0]
    puts_long = sum(l.quantity for l in legs if l.contract.kind == "put" and l.quantity > 0)
    uncovered = max(0, sum(-l.quantity for l in puts_short) - puts_long)
    need_cash = 0.0
    if uncovered:
        for l in sorted(puts_short, key=lambda x: -x.contract.strike):
            take = min(uncovered, -l.quantity)
            need_cash += take * l.contract.multiplier * l.contract.strike
            uncovered -= take
            if not uncovered:
                break
    out.append(Check("short_puts_secured", need_cash <= cash,
                     "Every short put is covered by a long put or by cash" if need_cash <= cash
                     else f"Short puts need {need_cash:,.0f} USD of cash to be secured, the account has {cash:,.0f} USD"))
    return out


def check_strategy(legs: Sequence[Leg], quotes: dict[str, OptionQuote], cfg: OptionsConfig, equity: float, cash: float,
                   now: datetime, shares_held: int = 0, premium_open: float = 0.0, stock: Optional[StockLeg] = None) -> list[Check]:
    """All checks for opening a position. `premium_open` is premium already paid on open positions."""
    r = cfg.risk
    out: list[Check] = []
    today = ensure_utc(now).astimezone(ZoneInfo(MARKET_TZ)).date()
    for l in legs:
        c, q = l.contract, quotes.get(l.contract.symbol)
        dte = c.days_to_expiry(today)
        out.append(Check(f"{c.symbol} days_to_expiry", dte >= r.min_days_to_expiry,
                         f"{dte} days to expiry, at least {r.min_days_to_expiry} needed"))
        if c.expiry == today:
            cutoff = local_to_utc(today, cfg.expiry_day_cutoff_local, MARKET_TZ)
            out.append(Check(f"{c.symbol} expiry_day_cutoff", ensure_utc(now) < cutoff,
                             f"No new orders on expiry day after {cfg.expiry_day_cutoff_local} ET"))
        if q is None or q.mid is None:
            out.append(Check(f"{c.symbol} quote", False, "No usable bid and ask for this contract"))
            continue
        out.append(Check(f"{c.symbol} spread", q.spread_pct_of_mid <= r.max_spread_pct_of_mid + 1e-9,  # type: ignore[operator]
                         f"Bid-ask spread is {q.spread_pct_of_mid:.0%} of the midpoint, at most {r.max_spread_pct_of_mid:.0%} allowed"))
        if q.open_interest is not None:
            out.append(Check(f"{c.symbol} open_interest", q.open_interest >= r.min_open_interest,
                             f"Open interest {q.open_interest}, at least {r.min_open_interest} needed"))
        else:
            out.append(Check(f"{c.symbol} open_interest", False, "Open interest not reported"))
    if not r.allow_uncovered_short_calls or not r.allow_uncovered_short_puts:
        for chk in _covered(legs, shares_held, cash):
            if (chk.name == "short_calls_covered" and not r.allow_uncovered_short_calls) or \
               (chk.name == "short_puts_secured" and not r.allow_uncovered_short_puts):
                out.append(chk)
    prof = profile(legs, stock)
    if prof.max_loss is None:
        out.append(Check("max_loss", False, "The possible loss has no limit"))
    else:
        cap = r.max_loss_pct_equity * equity
        out.append(Check("max_loss", prof.max_loss <= cap,
                         f"Largest possible loss {prof.max_loss:,.0f} USD, at most {cap:,.0f} USD ({r.max_loss_pct_equity:.0%} of the account)"))
    paid = max(prof.net_premium, 0.0)
    cap1 = r.max_premium_pct_equity * equity
    out.append(Check("premium", paid <= cap1, f"Premium paid {paid:,.0f} USD, at most {cap1:,.0f} USD ({r.max_premium_pct_equity:.0%} of the account)"))
    cap2 = r.max_total_premium_pct_equity * equity
    out.append(Check("total_premium", premium_open + paid <= cap2,
                     f"Premium across all option positions {premium_open + paid:,.0f} USD, at most {cap2:,.0f} USD"))
    return out


def passed(checks: Sequence[Check]) -> bool:
    return all(c.passed for c in checks)


# Order shape for Alpaca, built but never sent from here. Sending waits until the read-only
# check against a live Alpaca account has passed (config/capabilities.yaml, broker_paper level).
def alpaca_order(legs: Sequence[Leg], limit_price: float, client_order_id: str) -> dict:
    """A day limit order in Alpaca's documented form. One leg is a plain order. Several legs are a
    multi-leg ("mleg") order with leg ratios in lowest terms, as Alpaca requires."""
    if not legs:
        raise ValueError("an order needs at least one leg")
    if limit_price <= 0:
        raise ValueError("a limit price must be positive. A net credit is sent as a positive price with the selling legs")
    unders = {l.contract.underlying for l in legs}
    if len(unders) != 1:
        raise ValueError("every leg must be on the same underlying")
    def intent(q: int) -> str:
        return "buy_to_open" if q > 0 else "sell_to_open"
    if len(legs) == 1:
        l = legs[0]
        return {"symbol": l.contract.symbol, "qty": str(abs(l.quantity)), "side": "buy" if l.quantity > 0 else "sell",
                "type": "limit", "limit_price": f"{limit_price:.2f}", "time_in_force": "day",
                "position_intent": intent(l.quantity), "client_order_id": client_order_id}
    g = 0
    for l in legs:
        g = math.gcd(g, abs(l.quantity))
    return {"order_class": "mleg", "qty": str(g), "type": "limit", "limit_price": f"{limit_price:.2f}", "time_in_force": "day",
            "client_order_id": client_order_id,
            "legs": [{"symbol": l.contract.symbol, "ratio_qty": str(abs(l.quantity) // g), "side": "buy" if l.quantity > 0 else "sell",
                      "position_intent": intent(l.quantity)} for l in legs]}
