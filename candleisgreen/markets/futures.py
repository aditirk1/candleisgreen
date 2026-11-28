"""Futures: contract months, last trading days, rolls, continuous series and a daily simulator.

Contract terms come from config/futures_contracts.yaml. Each field is an estimate until checked
against CME. The contract size (multiplier) is also cross-checked against the CFTC's own record of
it, and the simulator trades only a product whose size is confirmed one of those two ways.
Calendar results (contract to hold, roll, last trading day) are estimates from CME's published
rules until those rules are checked. Business days use the US holiday list in config/markets.yaml,
which covers only the years it lists; a date outside them is refused instead of guessed. No futures
price is fetched: settlement series come from files you upload. Results are daily approximations.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import yaml

from ..calendars import is_trading_day, rules
from ..core.config import FuturesConfig
from .options import Check

PATH = Path(__file__).resolve().parents[2] / "config" / "futures_contracts.yaml"
MONTH_CODES = "FGHJKMNQUVXZ"
SIM_LABEL = "Daily simulation on uploaded settlement prices. Calendar and tick terms are estimates until checked against CME. No broker was involved"
TERM_FIELDS = ("multiplier", "tick_size", "months", "last_trade_rule", "first_notice_rule", "settlement")


class CalendarGapError(LookupError):
    """The holiday list does not cover this year, so business days cannot be counted."""


class UnknownContractError(ValueError):
    pass


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    exchange: str
    multiplier: float
    tick_size: float
    tick_value_usd: float
    months: tuple[str, ...]
    last_trade_rule: str
    first_notice_rule: Optional[str]
    settlement: str
    cftc_code: str
    cot_dataset: str
    source: str
    cftc_size_factor: float
    checked_against_cme: dict

    @property
    def verified(self) -> bool:
        """Every term checked against CME."""
        return all(self.checked_against_cme.get(k) for k in TERM_FIELDS)

    @property
    def calendar_checked(self) -> bool:
        return all(self.checked_against_cme.get(k) for k in ("months", "last_trade_rule", "first_notice_rule"))


@lru_cache(maxsize=1)
def products() -> dict[str, Product]:
    raw = yaml.safe_load(PATH.read_text())["products"]
    return {k: Product(code=k, **{**v, "months": tuple(v["months"])}) for k, v in raw.items()}


def cftc_size(contract_units: str) -> Optional[float]:
    """The contract size in a CFTC record: the dollar amount where one is given ('$50 X S&P 500 INDEX',
    'NASDAQ 100 STOCK INDEX X $20', '$100,000 FACE VALUE'), otherwise the first number ('1,000 BARRELS')."""
    import re
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", contract_units) or re.search(r"([\d,]+(?:\.\d+)?)", contract_units)
    return float(m.group(1).replace(",", "")) if m else None


@dataclass(frozen=True)
class TermStatus:
    field: str
    value: object
    status: str   # checked (against CME), cross_checked (against the CFTC), mismatch, estimated
    note: str


def term_status(code: str, cftc_units: Optional[str] = None) -> list[TermStatus]:
    """How far each contract term can be trusted. Only checked and cross_checked are authoritative."""
    p = products()[code]
    out = []
    for f in TERM_FIELDS:
        value = getattr(p, f)
        when = p.checked_against_cme.get(f)
        if when:
            out.append(TermStatus(f, value, "checked", f"Checked against CME on {when}"))
            continue
        if f == "multiplier" and cftc_units:
            size = cftc_size(cftc_units)
            implied = None if size is None else size * p.cftc_size_factor
            if implied is not None and abs(implied - p.multiplier) < 1e-9:
                out.append(TermStatus(f, value, "cross_checked", f"Matches the CFTC contract size {cftc_units.strip('()')}"))
            else:
                out.append(TermStatus(f, value, "mismatch", f"Does not match the CFTC contract size {cftc_units.strip('()')}"))
            continue
        out.append(TermStatus(f, value, "estimated", "From CME's published specification, not yet checked against CME"))
    return out


def multiplier_confirmed(code: str, cftc_units: Optional[str] = None) -> bool:
    return next(t for t in term_status(code, cftc_units) if t.field == "multiplier").status in ("checked", "cross_checked")


@lru_cache(maxsize=1)
def _covered_years() -> frozenset[int]:
    return frozenset(int(str(h)[:4]) for h in rules()["XNYS"].get("holidays", []))


def business_day(d: date) -> bool:
    if d.year not in _covered_years():
        raise CalendarGapError(f"no holiday list for {d.year} in config/markets.yaml")
    return is_trading_day(d)


def _last_business_day(year: int, month: int) -> date:
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    while not business_day(d):
        d -= timedelta(days=1)
    return d


def _back(d: date, n: int) -> date:
    while n:
        d -= timedelta(days=1)
        if business_day(d):
            n -= 1
    return d


def contract_code(product: str, year: int, month: int) -> str:
    return f"{product}{MONTH_CODES[month - 1]}{year % 100:02d}"


def parse_code(code: str) -> tuple[str, int, int]:
    """'ESZ26' to ('ES', 2026, 12). Two-digit years are read as 20xx."""
    code = code.strip().upper()
    prod, m, yy = code[:-3], code[-3], code[-2:]
    if prod not in products() or m not in MONTH_CODES or not yy.isdigit():
        raise UnknownContractError(f"'{code}' is not a known contract code")
    return prod, 2000 + int(yy), MONTH_CODES.index(m) + 1


def last_trade_day(product: str, year: int, month: int) -> date:
    rule = products()[product].last_trade_rule
    if rule == "third_friday":
        d = date(year, month, 1)
        d += timedelta(days=(4 - d.weekday()) % 7 + 14)
        while not business_day(d):
            d -= timedelta(days=1)
        return d
    if rule == "cl_before_25th":
        py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
        d25 = date(py, pm, 25)
        return _back(d25, 3 if business_day(d25) else 4)
    if rule == "third_last_business_day":
        return _back(_last_business_day(year, month), 2)
    if rule == "seventh_business_day_before_last":
        return _back(_last_business_day(year, month), 7)
    raise UnknownContractError(f"no rule '{rule}'")


def first_notice_day(product: str, year: int, month: int) -> Optional[date]:
    rule = products()[product].first_notice_rule
    if rule is None:
        return None
    if rule == "last_business_day_prior_month":
        py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
        return _last_business_day(py, pm)
    raise UnknownContractError(f"no rule '{rule}'")


def roll_date(product: str, year: int, month: int, cfg: FuturesConfig) -> date:
    """Leave a contract this many business days before its last trade or first notice, whichever is first."""
    ends = [d for d in (last_trade_day(product, year, month), first_notice_day(product, year, month)) if d]
    return _back(min(ends), cfg.roll_business_days_before_last_trade)


def listed_after(product: str, day: date, count: int) -> list[tuple[int, int]]:
    months = [MONTH_CODES.index(m) + 1 for m in products()[product].months]
    out, y = [], day.year
    while len(out) < count:
        for m in months:
            if (y, m) >= (day.year, day.month):
                out.append((y, m))
        y += 1
    return out[:count]


def front_contract(product: str, day: date, cfg: FuturesConfig) -> tuple[str, date]:
    """The contract to hold on `day` under the roll rule, and the date it rolls."""
    for y, m in listed_after(product, day, 6):
        r = roll_date(product, y, m, cfg)
        if day < r:
            return contract_code(product, y, m), r
    raise UnknownContractError("no listed contract found")


def parse_settlements(text: str) -> dict[str, list[tuple[date, float]]]:
    """CSV with columns date, contract, settle (for example 2026-11-20,ESZ26,6012.25)."""
    out: dict[str, list[tuple[date, float]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        keys = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not keys.get("settle"):
            continue
        code = keys["contract"].upper()
        parse_code(code)
        out.setdefault(code, []).append((date.fromisoformat(keys["date"]), float(keys["settle"])))
    for v in out.values():
        v.sort()
    return out


@dataclass(frozen=True)
class ContinuousPoint:
    day: date
    contract: str
    raw: float
    adjusted: float
    rolled: bool


def continuous(product: str, series: dict[str, list[tuple[date, float]]], cfg: FuturesConfig,
               method: Optional[str] = None) -> list[ContinuousPoint]:
    """Join contracts on the roll rule. Back adjustment shifts history by each roll gap, ratio adjustment
    scales it, unadjusted leaves the gaps. A day with no settlement for the contract held is skipped."""
    method = method or cfg.continuous_method
    px = {c: dict(rows) for c, rows in series.items()}
    days = sorted({d for rows in series.values() for d, _ in rows})
    raw: list[tuple[date, str, float, bool]] = []
    prev = None
    for d in days:
        code, _ = front_contract(product, d, cfg)
        if d not in px.get(code, {}):
            continue
        raw.append((d, code, px[code][d], prev is not None and code != prev))
        prev = code
    adj = [r[2] for r in raw]
    for i, (d, code, p, rolled) in enumerate(raw):
        if not rolled or method == "unadjusted":
            continue
        old = raw[i - 1][1]
        old_px = px[old].get(d)
        if old_px is None:
            continue  # no overlap day, so the gap cannot be measured and history is left as it is
        for j in range(i):
            adj[j] = adj[j] + (p - old_px) if method == "back_adjusted" else adj[j] * (p / old_px)
    return [ContinuousPoint(d, c, p, a, r) for (d, c, p, r), a in zip(raw, adj)]


@dataclass
class FuturesSimulator:
    """Daily mark to market. Variation margin moves cash each day. Below maintenance margin, the
    position is closed at that day's settlement."""
    cfg: FuturesConfig
    cash: float
    confirmed: frozenset = frozenset()   # products whose contract size is checked against CME or the CFTC
    positions: dict[str, int] = field(default_factory=dict)
    last_settle: dict[str, float] = field(default_factory=dict)
    events: list = field(default_factory=list)

    def check(self, code: str, contracts: int, settle: float, initial_margin: Optional[float], equity: float) -> list[Check]:
        prod = products()[parse_code(code)[0]]
        ok = prod.code in self.confirmed
        out = [Check("multiplier_confirmed", ok, f"Contract size {prod.multiplier:g} USD per point "
                     + ("confirmed" if ok else "not confirmed against CME or the CFTC, so profit and loss cannot be trusted"))]
        if initial_margin is None:
            return out + [Check("margin_known", False, "Margin requirement NOT AVAILABLE. Enter the current CME margin for this contract")]
        held = self.positions.get(code, 0) + contracts
        m = abs(held) * initial_margin
        cap = self.cfg.risk.max_margin_pct_equity * equity
        out.append(Check("margin", m <= cap, f"Margin {m:,.0f} USD, at most {cap:,.0f} USD ({self.cfg.risk.max_margin_pct_equity:.0%} of the account)"))
        notional = abs(held) * settle * prod.multiplier
        cap2 = self.cfg.risk.max_notional_pct_equity * equity
        out.append(Check("notional", notional <= cap2, f"Contract value {notional:,.0f} USD, at most {cap2:,.0f} USD"))
        return out

    def trade(self, code: str, contracts: int, settle: float, initial_margin: Optional[float]) -> tuple[str, list[Check]]:
        checks = self.check(code, contracts, settle, initial_margin, self.cash)
        if not all(c.passed for c in checks):
            return "blocked", checks
        self.positions[code] = self.positions.get(code, 0) + contracts
        self.last_settle[code] = settle
        if not self.positions[code]:
            del self.positions[code]
        return "filled", checks

    def mark(self, day: date, settles: dict[str, float], maintenance: dict[str, float]) -> list[str]:
        notes = []
        for code, n in list(self.positions.items()):
            s = settles.get(code)
            if s is None:
                notes.append(f"{code}: no settlement on {day}, not marked")
                continue
            mult = products()[parse_code(code)[0]].multiplier
            vm = n * (s - self.last_settle[code]) * mult
            self.cash += vm
            self.last_settle[code] = s
            self.events.append((day, code, "variation_margin", vm))
        need = sum(abs(n) * maintenance.get(c, 0.0) for c, n in self.positions.items())
        if self.positions and self.cash < need:
            for code in list(self.positions):
                self.events.append((day, code, "closed_on_margin_call", self.positions.pop(code)))
            notes.append(f"Account fell below maintenance margin ({self.cash:,.0f} USD against {need:,.0f} USD). Positions closed at settlement")
        return notes
