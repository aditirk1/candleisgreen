"""API for options, crypto, forex and futures. Read only toward every source. No broker orders.

Every response names its source and its limits. Where data needs a key or a license that is
not in place, the response says NOT AVAILABLE with the reason and the step that fixes it.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.capabilities import LEVELS, load_capabilities
from ..core.config import AppConfig
from ..core.licenses import load_licenses
from ..markets import crypto as cr
from ..markets import futures as fu
from ..markets import options as op
from ..markets.service import STORE_FILE, load_settlements, record_cot, record_crypto
from ..markets.store import MarketStore

ASSET_SPEC = Path(__file__).resolve().parents[2] / "config" / "asset_classes.yaml"


class LegBody(BaseModel):
    symbol: Optional[str] = None
    underlying: Optional[str] = None
    expiry: Optional[date] = None
    kind: Optional[str] = None
    strike: Optional[float] = None
    quantity: int
    premium: float


class StrategyBody(BaseModel):
    legs: list[LegBody]
    stock_quantity: int = 0
    stock_cost: float = 0.0


class CryptoOrderBody(BaseModel):
    client_order_id: str
    side: str
    symbol: str
    notional: float


class SettlementBody(BaseModel):
    text: str


def _bars_json(bars) -> list[dict]:
    return [{"date": b.start.date().isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in bars]


def build(workdir: Path, cfg: AppConfig, clock) -> APIRouter:
    r = APIRouter()
    store = MarketStore(Path(workdir) / STORE_FILE, shared=True)
    from ..markets.crypto_ledger import CryptoPractice, OrderIdReusedError
    practice = CryptoPractice(Path(workdir) / "crypto_practice.sqlite", cfg.assets.crypto, cfg.execution.simulator_starting_equity_usd)

    def crypto_api():
        from ..sources.alpaca_crypto import AlpacaCrypto, transport_from_env
        return AlpacaCrypto(transport_from_env(cfg.sources.alpaca), cfg.sources.alpaca, cfg.assets.crypto)

    @r.get("/api/assets/levels")
    def levels():
        caps = load_capabilities()
        spec = yaml.safe_load(ASSET_SPEC.read_text())["asset_classes"]
        out = []
        for a in spec:
            cap = caps.get(a["capability"])
            lv = cap.levels
            out.append({"id": a["id"], "label": a["label"], "screen": a.get("screen"),
                        "levels": [{"key": k, "label": label, "state": getattr(lv, k).state.value, "note": getattr(lv, k).note,
                                    "checked": getattr(lv, k).checked} for k, label in LEVELS] if lv else []})
        return {"asset_classes": out, "order": [label for _, label in LEVELS]}

    # Options
    @r.get("/api/assets/options/chain")
    def options_chain(underlying: str, days: int = 45):
        if not (os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY")):
            return {"status": "NOT AVAILABLE", "reason": "The options chain needs your free Alpaca paper keys in APCA_API_KEY_ID and APCA_API_SECRET_KEY"}
        from ..sources.alpaca import HttpTransport
        from ..sources.alpaca_options import AlpacaOptions
        api = AlpacaOptions(HttpTransport(cfg.sources.alpaca), cfg.sources.alpaca, cfg.assets.options)
        today = clock().date()
        try:
            info = api.contracts(underlying, today, today + timedelta(days=days))
            quotes = api.chain(underlying, today, today + timedelta(days=days), open_interest={i.contract.symbol: i.open_interest for i in info if i.open_interest is not None})
        except Exception as exc:  # noqa: BLE001
            return {"status": "NOT AVAILABLE", "reason": f"Alpaca did not answer: {type(exc).__name__}"}
        rows = []
        for i in sorted(info, key=lambda x: (x.contract.expiry, x.contract.strike, x.contract.kind)):
            q = quotes.get(i.contract.symbol)
            rows.append({"symbol": i.contract.symbol, "expiry": i.contract.expiry.isoformat(), "kind": i.contract.kind, "strike": i.contract.strike,
                         "bid": q.bid if q else None, "ask": q.ask if q else None, "last": q.last if q else None,
                         "iv": q.implied_volatility if q else None, "greeks": q.greeks if q else None, "open_interest": i.open_interest,
                         "quote_time": q.quote_time.isoformat() if q and q.quote_time else None})
        return {"status": "OK", "underlying": underlying.upper(), "feed": cfg.assets.options.feed, "rows": rows,
                "note": "Indicative feed: a free, modified version of exchange quotes. Not executable prices. Greeks are Alpaca's Black-Scholes values"}

    @r.post("/api/assets/options/strategy")
    def options_strategy(body: StrategyBody):
        try:
            legs = []
            for l in body.legs:
                c = op.parse_occ(l.symbol) if l.symbol else op.OptionContract(
                    op.format_occ(l.underlying or "", l.expiry, l.kind, l.strike), (l.underlying or "").upper(), l.expiry, l.kind, l.strike)  # type: ignore[arg-type]
                legs.append(op.Leg(c, l.quantity, l.premium))
            stock = op.StockLeg(body.stock_quantity, body.stock_cost) if body.stock_quantity else None
            p = op.profile(legs, stock, points=80)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
        return {"net_premium": p.net_premium, "max_loss": p.max_loss, "max_gain": p.max_gain, "breakevens": list(p.breakevens),
                "points": [{"price": x, "pnl": y} for x, y in p.points],
                "note": "Profit or loss at expiry for the premiums you entered. Not a forecast"}

    @r.get("/api/assets/options/model")
    def options_model(kind: str, spot: float, strike: float, days: int, volatility: float, rate: float = 0.0, dividend_yield: float = 0.0):
        if kind not in ("call", "put"):
            raise HTTPException(400, "kind must be call or put")
        try:
            v = op.black_scholes(kind, spot, strike, days / 365, volatility, rate, dividend_yield)  # type: ignore[arg-type]
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"price": v.price, "delta": v.delta, "gamma": v.gamma, "theta_per_day": v.theta_per_day,
                "vega_per_vol_point": v.vega_per_vol_point, "rho_per_rate_point": v.rho_per_rate_point, "inputs": v.inputs, "label": v.label}

    # Crypto
    @r.get("/api/assets/crypto")
    def crypto(symbol: Optional[str] = None):
        now = clock()
        series = {s[1]: s for s in store.symbols("crypto") if s[0] == "alpaca_us"}
        rows = []
        for sym in cfg.assets.crypto.symbols:
            bars = store.bars("alpaca_us", sym, "1Day", now)
            st = cr.series_stats(bars)
            rows.append({"symbol": sym, "days": len(bars), "last_date": bars[-1].start.date().isoformat() if bars else None,
                         "close": bars[-1].close if bars else None,
                         "change_30d": (bars[-1].close / bars[-31].close - 1) if len(bars) > 31 else None,
                         "volatility": st.annual_volatility if st else None, "max_drawdown": st.max_drawdown if st else None,
                         "median_volume": st.median_daily_volume if st else None})
        sel = symbol or cfg.assets.crypto.symbols[0]
        chart = _bars_json(store.bars("alpaca_us", sel, "1Day", now)) if sel in series else []
        return {"rows": rows, "symbol": sel, "bars": chart, "recorded": bool(series),
                "source": "Alpaca crypto data, Alpaca US book. Volume is Alpaca's own, not the whole market",
                "simulator": {"cash": practice.state()[0], "holdings": practice.state()[1], "fills": practice.fills(10)}}

    @r.post("/api/assets/crypto/refresh")
    def crypto_refresh():
        try:
            return record_crypto(store, crypto_api(), cfg, clock())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Could not reach Alpaca crypto data ({type(exc).__name__}). Check the internet connection")

    @r.get("/api/assets/crypto/book")
    def crypto_book(symbol: str):
        try:
            book = crypto_api().latest_orderbooks([symbol]).get(symbol)
        except Exception as exc:  # noqa: BLE001
            return {"status": "NOT AVAILABLE", "reason": f"Could not reach Alpaca crypto data ({type(exc).__name__})"}
        q = cr.book_quality(book or {}, cfg.assets.crypto)
        if q is None:
            return {"status": "NOT AVAILABLE", "reason": "No usable order book"}
        fresh = cr.check_freshness(q, clock(), cfg.assets.crypto)
        return {"status": "OK", "symbol": symbol, "mid": q.mid, "spread_bps": q.spread_bps, "bid_depth_usd": q.bid_depth_usd,
                "ask_depth_usd": q.ask_depth_usd, "time": q.book_time, "fresh": fresh.passed, "freshness": fresh.reason,
                "band_bps": cfg.assets.crypto.risk.max_spread_bps,
                "taker_fee_bps": cr.fee_bps(cfg.assets.crypto, practice.volume_30d(clock()), maker=False)}

    @r.post("/api/assets/crypto/simulate")
    def crypto_simulate(body: CryptoOrderBody):
        if body.side not in ("buy", "sell") or body.notional <= 0:
            raise HTTPException(400, "side must be buy or sell and the amount positive")
        cash, holdings = practice.state()
        try:
            books = crypto_api().latest_orderbooks(sorted({body.symbol, *holdings}))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Could not reach Alpaca crypto data ({type(exc).__name__})")
        now = clock()
        mids = {s: q.mid for s, b in books.items() if (q := cr.book_quality(b, cfg.assets.crypto)) and cr.check_freshness(q, now, cfg.assets.crypto).passed}
        try:
            out = practice.order(body.client_order_id, body.side, body.symbol, body.notional, books.get(body.symbol) or {}, now, mids)
        except (OrderIdReusedError, ValueError) as exc:
            raise HTTPException(409, str(exc))
        return out | {"label": cr.SIM_LABEL}

    # Forex
    @r.get("/api/assets/forex")
    def forex():
        lic = load_licenses().licenses["oanda_practice"]
        has_token = bool(os.environ.get("OANDA_PRACTICE_TOKEN") and os.environ.get("OANDA_PRACTICE_ACCOUNT_ID"))
        steps = []
        if not has_token:
            steps.append("Open a free OANDA fxTrade Practice account, create a personal access token, and set OANDA_PRACTICE_TOKEN and OANDA_PRACTICE_ACCOUNT_ID")
        if lic.research.value != "permitted":
            steps.append("Read OANDA's API license when you create the token. If it allows your personal research, mark the OANDA practice license as permitted")
        stored = {s[1]: s for s in store.symbols("fx")}
        return {"status": "OK" if not steps else "NOT AVAILABLE", "steps": steps, "license_file": "config/licenses.yaml, entry oanda_practice", "instruments": list(cfg.assets.forex.instruments),
                "stored": {k: {"days": v[2], "last": v[3].isoformat() if v[3] else None} for k, v in stored.items()},
                "reference": "Daily reference rates from FRED stay on Markets, Global. They have no bid or ask, so they cannot model spreads",
                "limits": {"max_spread_pips": cfg.assets.forex.risk.max_spread_pips, "max_notional_pct_equity": cfg.assets.forex.risk.max_notional_pct_equity,
                           "max_gross_leverage": cfg.assets.forex.risk.max_gross_leverage}}

    # Futures
    @r.get("/api/assets/futures")
    def futures():
        from ..sources.cftc import positioning, percentile
        now = clock()
        today = now.date()
        out = []
        for code, p in fu.products().items():
            row = {"code": code, "name": p.name, "exchange": p.exchange, "multiplier": p.multiplier, "tick_size": p.tick_size,
                   "tick_value_usd": p.tick_value_usd, "settlement": p.settlement, "verified": p.verified, "source": p.source}
            try:
                front, roll = fu.front_contract(code, today, cfg.assets.futures)
                _, y, m = fu.parse_code(front)
                row |= {"front": front, "roll_date": roll.isoformat(), "last_trade": fu.last_trade_day(code, y, m).isoformat()}
            except fu.CalendarGapError as exc:
                row |= {"front": None, "calendar_reason": str(exc)}
            reports = store.reports(p.cot_dataset, p.cftc_code, now)
            if reports:
                rep, body, usable = reports[-1]
                oi, groups = positioning(body, p.cot_dataset)
                window = reports[-cfg.assets.futures.cot_percentile_window_weeks:]
                hist = [positioning(b, p.cot_dataset)[1][0].net_pct_oi for _, b, _ in window]
                prev = positioning(reports[-2][1], p.cot_dataset)[1] if len(reports) > 1 else None
                row["cot"] = {"report_date": rep.isoformat(), "usable_from": usable.isoformat(), "open_interest": oi, "reports": len(reports),
                              "groups": [{"label": g.label, "long": g.long, "short": g.short, "net": g.net, "net_pct_oi": g.net_pct_oi,
                                          "week_change": (g.net - prev[i].net) if prev else None} for i, g in enumerate(groups)],
                              "lead_percentile": percentile(hist, hist[-1]), "lead_group": groups[0].label, "window_reports": len(window)}
            uploaded = [s for s in store.symbols("future") if fu.parse_code(s[1])[0] == code]
            row["uploaded_contracts"] = [{"contract": s[1], "days": s[2]} for s in uploaded]
            out.append(row)
        return {"products": out, "cot_source": "CFTC Commitments of Traders, futures only. Public domain",
                "prices": "No futures prices are fetched. CME's terms could not be read. Upload settlement files you downloaded yourself"}

    @r.post("/api/assets/futures/cot/refresh")
    def cot_refresh():
        from ..sources.public_http import PublicTransport
        try:
            return record_cot(store, PublicTransport(), cfg, clock())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Could not reach the CFTC reporting site ({type(exc).__name__}). Check the internet connection")

    @r.post("/api/assets/futures/settlements")
    def settlements(body: SettlementBody):
        try:
            return load_settlements(store, body.text, clock())
        except (ValueError, KeyError, fu.UnknownContractError) as exc:
            raise HTTPException(400, f"Could not read the file: {exc}. Columns needed: date, contract, settle")

    @r.get("/api/assets/futures/continuous")
    def futures_continuous(product: str, method: Optional[str] = None):
        now = clock()
        series = {}
        for venue, code, _, _ in store.symbols("future"):
            if fu.parse_code(code)[0] == product.upper():
                series[code] = [(b.start.date(), b.close) for b in store.bars(venue, code, "1Day", now)]
        if not series:
            return {"status": "NOT AVAILABLE", "reason": "No settlement prices uploaded for this product"}
        try:
            pts = fu.continuous(product.upper(), series, cfg.assets.futures, method)
        except fu.CalendarGapError as exc:
            return {"status": "NOT AVAILABLE", "reason": str(exc)}
        return {"status": "OK", "method": method or cfg.assets.futures.continuous_method, "label": fu.SIM_LABEL,
                "points": [{"date": p.day.isoformat(), "contract": p.contract, "raw": p.raw, "adjusted": p.adjusted, "rolled": p.rolled} for p in pts]}

    return r
