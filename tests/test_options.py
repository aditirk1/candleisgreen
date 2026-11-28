"""Options: symbols, payoffs, the theoretical model, expiry, risk checks, the simulator and the Alpaca client.

Quotes here are invented test values in the documented response shape. No test treats them
as market data.
"""
from datetime import date, datetime, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.markets.options import (Leg, OptionQuote, OptionSymbolError, StockLeg, black_scholes, check_strategy,
                                           format_occ, parse_occ, passed, profile, settle_at_expiry)
from candleisgreen.markets.options_sim import INDICATIVE_LABEL, OptionsSimulator
from candleisgreen.sources.alpaca_options import (AlpacaOptions, HistoryNotAvailableError, SubscriptionRequiredError,
                                                  parse_contract)

CFG = load_config()
OPT = CFG.assets.options
NOW = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)  # 10:00 ET
C150 = parse_occ("UPCO261218C00150000")
C160 = parse_occ("UPCO261218C00160000")
P140 = parse_occ("UPCO261218P00140000")


def q(sym, bid, ask, oi=500, feed="indicative"):
    return OptionQuote(sym, feed, bid, ask, NOW, open_interest=oi)


def test_occ_symbols_round_trip_and_reject_garbage():
    c = parse_occ("AAPL250117C00150000")
    assert (c.underlying, c.expiry, c.kind, c.strike) == ("AAPL", date(2025, 1, 17), "call", 150.0)
    assert format_occ("AAPL", date(2025, 1, 17), "call", 150) == "AAPL250117C00150000"
    assert format_occ("SPY", date(2026, 12, 18), "put", 612.5) == "SPY261218P00612500"
    for bad in ("AAPL", "AAPL250117X00150000", "TOOLONGROOT250117C00150000"):
        with pytest.raises(OptionSymbolError):
            parse_occ(bad)


def test_payoff_profiles_are_exact():
    long_call = profile([Leg(C150, 1, 5.0)])
    assert long_call.max_loss == 500 and long_call.max_gain is None and long_call.breakevens == (155.0,)
    spread = profile([Leg(C150, 1, 5.0), Leg(C160, -1, 2.0)])
    assert spread.max_loss == pytest.approx(300) and spread.max_gain == pytest.approx(700)
    assert spread.breakevens == (153.0,) and spread.net_premium == pytest.approx(300)
    naked = profile([Leg(C150, -1, 5.0)])
    assert naked.max_loss is None and naked.max_gain == pytest.approx(500)
    covered = profile([Leg(C160, -1, 2.0)], stock=StockLeg(100, 150.0))
    assert covered.max_loss == pytest.approx(14800) and covered.max_gain == pytest.approx(1200)


def test_black_scholes_matches_the_textbook_value_and_parity():
    c = black_scholes("call", 100, 100, 1.0, 0.2, 0.05)
    p = black_scholes("put", 100, 100, 1.0, 0.2, 0.05)
    assert c.price == pytest.approx(10.4506, abs=1e-4)
    assert c.price - p.price == pytest.approx(100 - 100 * 2.718281828 ** -0.05, abs=1e-6)
    assert 0 < c.delta < 1 and -1 < p.delta < 0 and c.gamma == pytest.approx(p.gamma)
    assert "Not a market price" in c.label


def test_expiry_exercises_and_assigns_only_in_the_money_by_the_threshold():
    ex = settle_at_expiry(C150, 2, 155.0, OPT.auto_exercise_threshold_usd)
    assert (ex.action, ex.share_change, ex.cash_change) == ("exercise", 200, -30000.0)
    asg = settle_at_expiry(P140, -1, 130.0, OPT.auto_exercise_threshold_usd)
    assert (asg.action, asg.share_change, asg.cash_change) == ("assignment", 100, -14000.0)
    short_call = settle_at_expiry(C150, -1, 151.0, OPT.auto_exercise_threshold_usd)
    assert (short_call.share_change, short_call.cash_change) == (-100, 15000.0)
    assert settle_at_expiry(C150, 1, 150.005, OPT.auto_exercise_threshold_usd).action == "expire"
    assert settle_at_expiry(P140, 1, 141.0, OPT.auto_exercise_threshold_usd).action == "expire"


def failed(checks):
    return {c.name.split(" ")[-1] for c in checks if not c.passed}


def test_risk_checks_block_unlimited_loss_and_unsecured_puts():
    quotes = {C150.symbol: q(C150.symbol, 4.9, 5.1), P140.symbol: q(P140.symbol, 1.9, 2.1)}
    naked = check_strategy([Leg(C150, -1, 4.9)], quotes, OPT, equity=1_000_000, cash=1_000_000, now=NOW)
    assert {"short_calls_covered", "max_loss"} <= failed(naked)
    covered = check_strategy([Leg(C150, -1, 4.9)], quotes, OPT, equity=1_000_000, cash=1_000_000, now=NOW, shares_held=100,
                             stock=StockLeg(100, 150.0))
    assert "short_calls_covered" not in failed(covered)
    put_poor = check_strategy([Leg(P140, -1, 1.9)], quotes, OPT, equity=1_000_000, cash=10_000, now=NOW)
    assert "short_puts_secured" in failed(put_poor)
    put_ok = check_strategy([Leg(P140, -1, 1.9)], quotes, OPT, equity=1_000_000, cash=14_000, now=NOW)
    assert "short_puts_secured" not in failed(put_ok)


def test_risk_checks_cap_loss_premium_expiry_spread_and_open_interest():
    quotes = {C150.symbol: q(C150.symbol, 4.9, 5.1)}
    small = check_strategy([Leg(C150, 1, 5.1)], quotes, OPT, equity=10_000, cash=10_000, now=NOW)
    assert {"max_loss", "premium"} <= failed(small)
    big = check_strategy([Leg(C150, 1, 5.1)], quotes, OPT, equity=100_000, cash=100_000, now=NOW)
    assert passed(big)
    assert "total_premium" in failed(check_strategy([Leg(C150, 1, 5.1)], quotes, OPT, 100_000, 100_000, NOW, premium_open=4_800))
    soon = parse_occ("UPCO261130C00150000")
    assert "days_to_expiry" in failed(check_strategy([Leg(soon, 1, 1.0)], {soon.symbol: q(soon.symbol, .9, 1.1)}, OPT, 1e6, 1e6, NOW))
    wide = {C150.symbol: q(C150.symbol, 3.0, 6.0)}
    assert "spread" in failed(check_strategy([Leg(C150, 1, 6.0)], wide, OPT, 1e6, 1e6, NOW))
    thin = {C150.symbol: q(C150.symbol, 4.9, 5.1, oi=10)}
    assert "open_interest" in failed(check_strategy([Leg(C150, 1, 5.1)], thin, OPT, 1e6, 1e6, NOW))
    assert "quote" in failed(check_strategy([Leg(C150, 1, 5.1)], {}, OPT, 1e6, 1e6, NOW))
    today = parse_occ("UPCO261127C00150000")
    late = datetime(2026, 11, 27, 20, 45, tzinfo=timezone.utc)  # 15:45 ET
    assert "expiry_day_cutoff" in failed(check_strategy([Leg(today, 1, 1.0)], {today.symbol: q(today.symbol, .9, 1.1)}, OPT, 1e6, 1e6, late))


def test_simulator_fills_at_the_quote_side_labels_indicative_and_settles_expiry():
    sim = OptionsSimulator(OPT, cash=100_000)
    quotes = {C150.symbol: q(C150.symbol, 4.9, 5.1), C160.symbol: q(C160.symbol, 1.9, 2.1)}
    res = sim.open([(C150, 1), (C160, -1)], quotes, NOW, equity=100_000)
    assert res.status == "filled" and [f.price for f in res.fills] == [5.1, 1.9]
    assert all(f.label == INDICATIVE_LABEL for f in res.fills)
    assert sim.cash == pytest.approx(100_000 - 510 + 190)
    blocked = sim.open([(C150, -3)], quotes, NOW, equity=100_000)
    assert blocked.status == "blocked" and sim.cash == pytest.approx(99_680)
    assert sim.unsettled(C150.expiry, {}) == [C150.symbol, C160.symbol]
    events = sim.expire(C150.expiry, {"UPCO": 165.0})
    assert {e.action for e in events} == {"exercise", "assignment"} and sim.shares["UPCO"] == 0
    assert sim.cash == pytest.approx(99_680 - 15_000 + 16_000) and not sim.positions


class Stub:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, base, path, params):
        self.calls.append((base, path, {k: v for k, v in params.items() if v is not None}))
        return self.pages.pop(0)


CONTRACT_ROW = {"id": "x", "symbol": "UPCO261218C00150000", "name": "UPCO Dec 18 2026 150 Call", "status": "active", "tradable": True,
                "expiration_date": "2026-12-18", "root_symbol": "UPCO", "underlying_symbol": "UPCO", "underlying_asset_id": "y",
                "type": "call", "style": "american", "strike_price": "150", "multiplier": "100", "size": "100",
                "open_interest": "1234", "open_interest_date": "2026-11-26", "close_price": "5.05", "close_price_date": "2026-11-26", "ppind": True}


def test_alpaca_client_parses_documented_shapes_pages_and_names_the_feed():
    t = Stub([{"option_contracts": [CONTRACT_ROW], "next_page_token": "p2"}, {"option_contracts": [], "next_page_token": None}])
    api = AlpacaOptions(t, CFG.sources.alpaca, OPT)
    rows = api.contracts("upco", date(2026, 12, 1), date(2026, 12, 31))
    assert rows[0].contract.strike == 150.0 and rows[0].open_interest == 1234 and rows[0].close_price == 5.05
    assert t.calls[0][0] == "https://paper-api.alpaca.markets" and t.calls[1][2]["page_token"] == "p2"
    snap = {"latestQuote": {"t": "2026-11-27T14:59:59.123456789Z", "bp": 4.9, "ap": 5.1, "bs": 3, "as": 4},
            "latestTrade": {"t": "2026-11-27T14:58:00Z", "p": 5.0}, "impliedVolatility": 0.31,
            "greeks": {"delta": 0.52, "gamma": 0.03, "theta": -0.05, "vega": 0.2, "rho": 0.04}}
    t2 = Stub([{"snapshots": {"UPCO261218C00150000": snap}, "next_page_token": None}])
    chain = AlpacaOptions(t2, CFG.sources.alpaca, OPT).chain("UPCO", open_interest={"UPCO261218C00150000": 1234})
    quote = chain["UPCO261218C00150000"]
    assert quote.feed == "indicative" and not quote.executable and quote.mid == pytest.approx(5.0)
    assert quote.greeks["delta"] == 0.52 and quote.open_interest == 1234 and quote.quote_time.microsecond == 123456
    assert t2.calls[0][2]["feed"] == "indicative" and t2.calls[0][1] == "/v1beta1/options/snapshots/UPCO"


def test_alpaca_client_refuses_paid_feeds_and_history_it_cannot_serve():
    with pytest.raises(SubscriptionRequiredError):
        AlpacaOptions(Stub([]), CFG.sources.alpaca, OPT.model_copy(update={"feed": "opra"}))
    api = AlpacaOptions(Stub([]), CFG.sources.alpaca, OPT)
    with pytest.raises(HistoryNotAvailableError):
        api.bars(["UPCO261218C00150000"], date(2023, 12, 1), NOW.replace(hour=10), NOW)
    with pytest.raises(HistoryNotAvailableError):
        api.bars(["UPCO261218C00150000"], date(2026, 1, 2), NOW.replace(hour=14, minute=50), NOW.replace(hour=14, minute=55))


def test_contract_strike_must_match_its_symbol():
    with pytest.raises(ValueError):
        parse_contract({**CONTRACT_ROW, "strike_price": "155"})


def test_order_builder_uses_alpacas_documented_shape_and_lowest_ratios():
    from candleisgreen.markets.options import alpaca_order
    single = alpaca_order([Leg(C150, 2, 5.1)], 5.1, "cid-1")
    assert single == {"symbol": C150.symbol, "qty": "2", "side": "buy", "type": "limit", "limit_price": "5.10",
                      "time_in_force": "day", "position_intent": "buy_to_open", "client_order_id": "cid-1"}
    spread = alpaca_order([Leg(C150, 4, 5.1), Leg(C160, -2, 1.9)], 3.2, "cid-2")
    assert spread["order_class"] == "mleg" and spread["qty"] == "2"
    assert [(x["ratio_qty"], x["side"], x["position_intent"]) for x in spread["legs"]] == [("2", "buy", "buy_to_open"), ("1", "sell", "sell_to_open")]
    with pytest.raises(ValueError):
        alpaca_order([Leg(C150, 1, 5.1), Leg(parse_occ("XYZ261218C00010000"), -1, 1)], 1, "cid-3")


def test_nothing_in_the_options_code_sends_an_order():
    import inspect
    import candleisgreen.markets.options as o
    import candleisgreen.markets.options_sim as s
    import candleisgreen.sources.alpaca_options as a
    for mod in (o, s, a):
        src = inspect.getsource(mod)
        assert ".send(" not in src and "/v2/orders" not in src
