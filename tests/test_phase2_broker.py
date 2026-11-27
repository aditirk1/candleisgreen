"""Phase 2 acceptance part 1: a duplicate submission is not repeated. Reconciliation fails closed."""
import pytest

from candleisgreen.broker.alpaca_paper import AlpacaPaperBroker
from candleisgreen.broker.alpaca_paper_fake import FakeAlpacaPaper
from candleisgreen.broker.base import LiveTradingDisabledError
from candleisgreen.broker.reconcile import reconcile
from candleisgreen.core.config import load_config
from candleisgreen.core.schemas import Venue
from candleisgreen.risk.engine import evaluate
from tests.conftest import make_ctx, make_intent

SYMBOLS = {"inst_TEST": "TEST"}


def _broker(fake):
    return AlpacaPaperBroker(fake, load_config().sources.alpaca, SYMBOLS.get,
                             {v: k for k, v in SYMBOLS.items()}.get)


def _approved(limits, **kw):
    intent = make_intent(venue=Venue.PAPER, **kw)
    return intent, evaluate(intent, make_ctx(), limits)


def test_marketable_limit_fills_and_carries_the_client_id(limits):
    fake = FakeAlpacaPaper()
    fake.set_quote("TEST", 51.18, 51.22)
    intent, decision = _approved(limits)
    ack = _broker(fake).submit(intent, decision, make_ctx().quote)
    assert ack.status == "filled" and ack.fills[0].price == 51.22
    assert fake.orders[intent.client_order_id]["type"] == "limit"


def test_duplicate_submission_is_not_repeated(limits):
    fake = FakeAlpacaPaper()
    fake.set_quote("TEST", 51.18, 51.22)
    broker = _broker(fake)
    intent, decision = _approved(limits)
    first = broker.submit(intent, decision, make_ctx().quote)
    second = broker.submit(intent, decision, make_ctx().quote)
    assert fake.post_calls == 1 and len(fake.orders) == 1
    assert second.status == first.status and "not resubmitted" in second.message


def test_lost_response_is_queried_not_resubmitted(limits):
    fake = FakeAlpacaPaper()
    fake.set_quote("TEST", 51.18, 51.22)
    fake.lose_response_after_accept = 1
    intent, decision = _approved(limits)
    ack = _broker(fake).submit(intent, decision, make_ctx().quote)
    assert fake.post_calls == 1 and len(fake.orders) == 1
    assert ack.status == "filled" and "found at the broker" in ack.message


def test_failure_before_acceptance_retries_once(limits):
    fake = FakeAlpacaPaper()
    fake.set_quote("TEST", 51.18, 51.22)
    fake.fail_before_accept = 1
    intent, decision = _approved(limits)
    ack = _broker(fake).submit(intent, decision, make_ctx().quote)
    assert fake.post_calls == 2 and len(fake.orders) == 1 and ack.status == "filled"


def test_two_uncertain_failures_leave_the_state_unknown(limits):
    fake = FakeAlpacaPaper()
    fake.fail_before_accept = 2
    intent, decision = _approved(limits)
    ack = _broker(fake).submit(intent, decision, make_ctx().quote)
    assert ack.status == "unknown" and fake.post_calls == 2 and not fake.orders


def test_resting_and_partial_fills(limits):
    fake = FakeAlpacaPaper()
    fake.set_quote("TEST", 51.18, 51.30)
    intent, decision = _approved(limits)  # limit 51.24 is below the ask
    assert _broker(fake).submit(intent, decision, make_ctx().quote).status == "accepted"
    assert _broker(fake).open_orders() == (intent.client_order_id,)
    fake2 = FakeAlpacaPaper()
    fake2.set_quote("TEST", 51.18, 51.22)
    fake2.partial_fraction = 0.5
    ack = _broker(fake2).submit(intent, decision, make_ctx().quote)
    assert ack.status == "partially_filled" and ack.fills[0].quantity == 24


def test_paper_adapter_refuses_simulation_orders_and_unapproved_ones(limits):
    fake = FakeAlpacaPaper()
    sim_intent = make_intent()
    with pytest.raises(LiveTradingDisabledError):
        _broker(fake).submit(sim_intent, evaluate(sim_intent, make_ctx(), limits), make_ctx().quote)
    intent = make_intent(venue=Venue.PAPER)
    blocked = evaluate(intent, make_ctx(kill_switch_engaged=True), limits)
    with pytest.raises(Exception):
        _broker(fake).submit(intent, blocked, make_ctx().quote)
    assert fake.post_calls == 0


def test_reconciliation():
    assert reconcile({"a": 10.0}, {"a": 10.0}).matched
    bad = reconcile({"a": 10.0, "b": 5.0}, {"a": 8.0})
    assert not bad.matched and len(bad.mismatches) == 2


# Through the executor on the PAPER venue -------------------------------------------------

def _paper_env(tmp_path):
    from candleisgreen.models.registry import ModelEntry, ModelRegistry
    from candleisgreen.trading import run_decision
    from tests.phase1_env import DECIDE_NOW, DECISION_DATE, SESSION_DATE, build_env

    env = build_env(tmp_path, "broker_paper_auto")
    run_decision(DECISION_DATE, SESSION_DATE, env.store, env.master, env.journal, env.cfg, DECIDE_NOW)
    # Test-only registry: nothing real holds the capital tier, so the paper path needs a stand-in.
    models = ModelRegistry(registry_version="test", models={"ts_momentum_252_21": ModelEntry(
        version="1.0.0", level="A", tier=5, family="trend", data_licenses=("alpaca_market_data",))})
    fake = FakeAlpacaPaper()
    quotes = None
    return env, models, fake


def _paper_broker(env, fake):
    return AlpacaPaperBroker(fake, env.cfg.sources.alpaca,
                             lambda iid: (env.master.symbols(iid) or [None])[-1], env.master.instrument_for_symbol)


def test_paper_execution_fills_and_reconciles(tmp_path):
    from candleisgreen.trading import execute_session
    from tests.phase1_env import EXEC_NOW, SESSION_DATE, quotes_for, risk_service

    env, models, fake = _paper_env(tmp_path)
    quotes = quotes_for(env, EXEC_NOW)
    for sym, q in quotes.quotes.items():
        fake.set_quote(sym, q.bid, q.ask)
    with risk_service(tmp_path / "risk") as (risk, _):
        res = execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes, risk, _paper_broker(env, fake),
                              env.store, env.master, env.cfg, venue=Venue.PAPER, models=models)
        again = execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes, risk, _paper_broker(env, fake),
                                env.store, env.master, env.cfg, venue=Venue.PAPER, models=models)
    assert res.submitted and again.submitted == ()
    assert fake.post_calls == len(res.submitted)
    assert reconcile(_paper_broker(env, fake).positions(), env.journal.positions()).matched
    assert env.journal.last_reconciliation() is True


def test_reconciliation_mismatch_blocks_every_order(tmp_path):
    from candleisgreen.trading import execute_session
    from tests.phase1_env import EXEC_NOW, SESSION_DATE, quotes_for, risk_service

    env, models, fake = _paper_env(tmp_path)
    quotes = quotes_for(env, EXEC_NOW)
    for sym, q in quotes.quotes.items():
        fake.set_quote(sym, q.bid, q.ask)
    fake.activities.append({"id": "x", "order_id": "outside", "symbol": "FLAT", "side": "buy", "qty": "10",
                            "price": "30", "transaction_time": "2026-11-20T14:00:00Z"})  # a position the journal lacks
    with risk_service(tmp_path / "risk") as (risk, _):
        res = execute_session(SESSION_DATE, EXEC_NOW, env.journal, quotes, risk, _paper_broker(env, fake),
                              env.store, env.master, env.cfg, venue=Venue.PAPER, models=models)
    assert res.submitted == () and fake.post_calls == 0
    assert all(any("account state unknown" in r for r in rs) for rs in res.blocked.values())
    assert env.journal.last_reconciliation() is False
