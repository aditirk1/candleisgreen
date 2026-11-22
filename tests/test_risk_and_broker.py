"""Phase 0: the risk engine fails closed and no route reaches real money."""
from datetime import timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from candleisgreen.broker.base import (
    LiveBroker, LiveTradingDisabledError, RiskApprovalRequiredError, assert_paper_endpoint,
)
from candleisgreen.broker.simulator import InternalSimulator
from candleisgreen.core.schemas import Quote, RiskVerdict, Side, Venue
from candleisgreen.risk import engine
from candleisgreen.risk.engine import evaluate
from tests.conftest import T0, make_ctx, make_intent

GOOD_QUOTE = Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0 - timedelta(seconds=3), feed="iex_realtime")


def test_clean_order_is_approved(limits):
    decision = evaluate(make_intent(), make_ctx(), limits)
    assert decision.verdict is RiskVerdict.APPROVED and decision.reasons == ()
    assert len(decision.checks_run) == len(engine.CHECKS)


BLOCKS = {
    "stale quote": dict(quote=Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0 - timedelta(seconds=16), feed="iex_realtime")),
    "no quote": dict(quote=None),
    "quote for another instrument": dict(quote=Quote(asset_id="inst_OTHER", bid=51.18, ask=51.22, quote_time=T0, feed="iex_realtime")),
    "wide spread": dict(quote=Quote(asset_id="inst_TEST", bid=50.00, ask=50.30, quote_time=T0, feed="iex_realtime")),
    "kill switch": dict(kill_switch_engaged=True),
    "kill switch unknown": dict(kill_switch_engaged=None),
    "market closed": dict(market_open=False),
    "market halted": dict(market_halted=True),
    "halt unknown": dict(market_halted=None),
    "broker disconnected": dict(broker_connected=False),
    "account unknown": dict(account_state_known=None),
    "equity unknown": dict(equity=None),
    "mapping uncertain": dict(instrument_mapping_certain=False),
    "daily loss stop": dict(equity=97_900.0),
    "position over 5%": dict(position_value=3_000.0),
    "position unknown": dict(position_value=None),
    "cluster over 20%": dict(cluster_value=19_000.0),
    "cluster unknown": dict(cluster_value=None),
    "order over 1% of ADV": dict(adv20_shares=4_000.0),
    "ADV unknown": dict(adv20_shares=None),
    "outside execution window": dict(in_execution_window=False),
    "execution window unknown": dict(in_execution_window=None),
    "delayed consolidated quote": dict(quote=Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0, feed="sip_delayed")),
    "quote with no size": dict(quote=Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0, feed="iex_realtime", ask_size=0)),
    "pending buys push position over 5%": dict(pending_position_value=3_000.0),
    "pending buys push cluster over 20%": dict(pending_cluster_value=19_000.0),
    "pending orders unknown": dict(pending_cluster_value=None),
}


@pytest.mark.parametrize("name", sorted(BLOCKS))
def test_each_failure_blocks_the_order(name, limits):
    decision = evaluate(make_intent(), make_ctx(**BLOCKS[name]), limits)
    assert decision.verdict is RiskVerdict.BLOCKED, name
    assert decision.reasons


def test_quote_at_the_limit_passes_and_just_over_fails(limits):
    at = Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0 - timedelta(seconds=15), feed="iex_realtime")
    over = Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0 - timedelta(seconds=15, milliseconds=1), feed="iex_realtime")
    assert evaluate(make_intent(), make_ctx(quote=at), limits).verdict is RiskVerdict.APPROVED
    assert evaluate(make_intent(), make_ctx(quote=over), limits).verdict is RiskVerdict.BLOCKED


def test_sell_that_would_go_short_is_blocked(limits):
    decision = evaluate(make_intent(side=Side.SELL), make_ctx(position_value=0.0), limits)
    assert decision.verdict is RiskVerdict.BLOCKED


def test_a_check_that_raises_blocks_the_order(limits, monkeypatch):
    def boom(intent, ctx, lim):
        raise ZeroDivisionError

    monkeypatch.setattr(engine, "CHECKS", engine.CHECKS + (("broken", boom),))
    decision = evaluate(make_intent(), make_ctx(), limits)
    assert decision.verdict is RiskVerdict.BLOCKED
    assert any("broken" in r for r in decision.reasons)


OPTIONAL_FIELDS = [
    "kill_switch_engaged", "market_open", "market_halted", "broker_connected", "account_state_known",
    "instrument_mapping_certain", "quote", "equity", "day_start_equity", "position_value",
    "cluster_value", "pending_position_value", "pending_cluster_value", "adv20_shares", "in_execution_window",
]


@settings(max_examples=200, deadline=None)
@given(missing=st.sets(st.sampled_from(OPTIONAL_FIELDS), min_size=1))
def test_any_missing_input_fails_closed(missing):
    from candleisgreen.core.config import load_config

    limits = load_config().risk.hard_limits
    ctx = make_ctx(**{name: None for name in missing})
    assert evaluate(make_intent(), ctx, limits).verdict is RiskVerdict.BLOCKED


def test_simulator_refuses_an_unapproved_order(limits):
    intent = make_intent()
    blocked = evaluate(intent, make_ctx(kill_switch_engaged=True), limits)
    sim = InternalSimulator(100_000)
    with pytest.raises(RiskApprovalRequiredError):
        sim.submit(intent, blocked, GOOD_QUOTE)
    other = evaluate(make_intent(quantity=10.0), make_ctx(), limits)
    with pytest.raises(RiskApprovalRequiredError):
        sim.submit(intent, other, GOOD_QUOTE)
    assert sim.positions() == {}


def test_duplicate_submission_is_not_repeated(limits):
    intent = make_intent()
    approved = evaluate(intent, make_ctx(), limits)
    sim = InternalSimulator(100_000)
    first = sim.submit(intent, approved, GOOD_QUOTE)
    second = sim.submit(intent, approved, GOOD_QUOTE)
    assert first == second
    assert sim.positions() == {"inst_TEST": 48.0}
    assert sim.cash == pytest.approx(100_000 - 48 * 51.22)


def test_simulator_rejects_a_paper_order(limits):
    intent = make_intent(venue=Venue.PAPER)
    approved = evaluate(intent, make_ctx(), limits)
    with pytest.raises(LiveTradingDisabledError):
        InternalSimulator(100_000).submit(intent, approved, GOOD_QUOTE)


def test_attempted_live_order_is_rejected(limits):
    """Failure fixture: attempted live order."""
    intent = make_intent()
    approved = evaluate(intent, make_ctx(), limits)
    with pytest.raises(LiveTradingDisabledError):
        LiveBroker().submit(intent, approved, GOOD_QUOTE)


@pytest.mark.parametrize("url", [
    "https://api.alpaca.markets/v2/orders",
    "https://paper-api.alpaca.markets.evil.example/v2/orders",
    "https://example.com/paper-api.alpaca.markets",
    "",
])
def test_non_paper_endpoints_are_refused(url):
    with pytest.raises(LiveTradingDisabledError):
        assert_paper_endpoint(url)


def test_paper_endpoint_is_accepted():
    assert_paper_endpoint("https://paper-api.alpaca.markets/v2/orders")


def test_limit_too_far_from_mid_is_blocked(limits):
    far = make_intent(limit=51.20 * 1.006)  # more than the 0.5% spread limit above mid
    assert evaluate(far, make_ctx(), limits).verdict is RiskVerdict.BLOCKED
    assert evaluate(make_intent(limit=51.24), make_ctx(), limits).verdict is RiskVerdict.APPROVED


def test_non_marketable_limit_rests_unfilled(limits):
    intent = make_intent(limit=51.19)  # below the ask
    approved = evaluate(intent, make_ctx(), limits)
    ack = InternalSimulator(100_000).submit(intent, approved, GOOD_QUOTE)
    assert ack.status == "accepted" and ack.fills == ()


def test_fill_records_slippage_against_arrival_mid(limits):
    intent = make_intent()
    ack = InternalSimulator(100_000).submit(intent, evaluate(intent, make_ctx(), limits), GOOD_QUOTE)
    assert ack.fills[0].slippage_bps == pytest.approx((51.22 - 51.20) / 51.20 * 1e4)
