"""Short selling: off by default, turned on only through Aditi's limit workflow, and checked on every order."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from candleisgreen.core.schemas import RiskVerdict, Side
from candleisgreen.risk.engine import evaluate, evaluate_portfolio
from candleisgreen.risk.limits import LimitBook, LimitChangeError
from tests.conftest import make_ctx, make_intent

UTC = timezone.utc
ON = dict(max_short_position_pct_equity=0.03, max_short_exposure_pct_equity=0.30, max_gross_exposure_pct_equity=1.0)


def _on(limits, **extra):
    return limits.model_copy(update={**ON, **extra})


def _sell(qty=48.0):
    return make_intent(quantity=qty, side=Side.SELL)


def verdict(intent, ctx, limits):
    d = evaluate(intent, ctx, limits)
    return d.verdict, " ".join(d.reasons)


def test_shorting_is_off_by_default(limits):
    v, why = verdict(_sell(), make_ctx(short_allowed=True), limits)
    assert v is RiskVerdict.BLOCKED and "short selling is off" in why


def test_a_short_within_every_limit_is_approved(limits):
    v, why = verdict(_sell(), make_ctx(short_allowed=True), _on(limits))  # 48 x 51.18, about 2.5% of equity
    assert v is RiskVerdict.APPROVED, why


@pytest.mark.parametrize("ctx, reason", [
    (dict(short_allowed=False), "easy to borrow"),
    (dict(short_allowed=None), "borrow status unknown"),
    (dict(short_allowed=True, position_value=-1_000.0), "short position"),        # 1,000 + 2,457 over 3%
    (dict(short_allowed=True, short_value=29_000.0), "short exposure"),           # 29,000 + 2,457 over 30%
    (dict(short_allowed=True, gross_value=98_000.0), "gross exposure"),           # over 100% of equity
    (dict(short_allowed=True, pending_short_position_value=1_000.0), "short position"),
    (dict(short_allowed=True, short_value=None), "short exposure cannot be evaluated"),
])
def test_each_short_rule_blocks(limits, ctx, reason):
    v, why = verdict(_sell(), make_ctx(**ctx), _on(limits))
    assert v is RiskVerdict.BLOCKED and reason in why


def test_one_order_cannot_flip_long_to_short(limits):
    v, why = verdict(_sell(100), make_ctx(short_allowed=True, position_value=2_000.0), _on(limits))
    assert v is RiskVerdict.BLOCKED and "cannot turn a long position into a short" in why
    v, _ = verdict(_sell(30), make_ctx(position_value=2_000.0), limits)  # a plain sale within the holding
    assert v is RiskVerdict.APPROVED


def test_covering_a_short_is_always_allowed_and_the_loss_stop_blocks_new_shorts(limits):
    down = dict(equity=97_000.0, day_start_equity=100_000.0)
    cover = make_intent(quantity=48.0, side=Side.BUY)
    v, why = verdict(cover, make_ctx(position_value=-2_500.0, short_value=2_500.0, gross_value=2_500.0, **down), limits)
    assert v is RiskVerdict.APPROVED, why  # shorting off and loss stop hit, covering still goes through
    v, why = verdict(_sell(), make_ctx(short_allowed=True, **down), _on(limits))
    assert v is RiskVerdict.BLOCKED and "daily loss stop" in why


def test_book_check_counts_shorts_gross(limits):
    on = _on(limits)
    assert evaluate_portfolio({"a": 0.04, "b": -0.03}, {"a": "c1", "b": "c2"}, on) == ()
    assert any("short selling is off" in r for r in evaluate_portfolio({"b": -0.01}, {"b": "c"}, limits))
    over = evaluate_portfolio({"a": 0.05, "b": -0.05}, {"a": "c1", "b": "c2"}, on)
    assert any("short 5.00% over limit" in r for r in over)
    cluster = evaluate_portfolio({f"l{i}": 0.04 for i in range(3)} | {f"s{i}": -0.03 for i in range(4)},
                                 {**{f"l{i}": "c" for i in range(3)}, **{f"s{i}": "c" for i in range(4)}}, on)
    assert any(r.startswith("cluster c") for r in cluster)  # 12% long plus 12% short is 24% gross


def test_turning_shorting_on_waits_24_hours_and_needs_aditi(tmp_path, limits):
    book = LimitBook(tmp_path, limits, 24)
    now = datetime(2026, 11, 27, 15, tzinfo=UTC)
    with pytest.raises(LimitChangeError):
        book.request("max_short_position_pct_equity", 0.03, "system:anything", now)
    assert book.request("max_short_position_pct_equity", 0.03, "user:aditi", now)["status"] == "WAITING"
    with pytest.raises(LimitChangeError):
        book.confirm("max_short_position_pct_equity", "user:aditi", now + timedelta(hours=23))
    assert book.confirm("max_short_position_pct_equity", "user:aditi", now + timedelta(hours=24))["status"] == "APPLIED"
    assert book.effective().max_short_position_pct_equity == 0.03
    assert book.request("max_short_position_pct_equity", 0.0, "user:aditi", now)["status"] == "APPLIED"  # off at once


def _enable_in_risk_state(state_dir):
    """Stands in for a confirmed change, as the workflow above would leave it after 24 hours."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "limit_changes.json").write_text(json.dumps({"pending": {}, "active": {
        k: {"value": v, "at": "2026-11-18T00:00:00+00:00", "by": "user:aditi"} for k, v in ON.items()}}))


def test_downtrends_are_shorted_end_to_end_once_turned_on(tmp_path):
    from candleisgreen import operations
    from tests.phase1_env import build_env, risk_service

    env = build_env(tmp_path, "auto_simulation")
    env.store.close()
    env.journal.close()
    _enable_in_risk_state(tmp_path / "risk")
    with risk_service(tmp_path / "risk") as (risk, _):
        cfg = env.cfg.model_copy(update={"execution": env.cfg.execution.model_copy(update={"risk_service_url": risk.base_url})})
        operations.decide(datetime(2026, 11, 19, 21, 31, tzinfo=UTC), tmp_path, cfg, fake=True)
        j = operations._journal(tmp_path, cfg)
        sides = {p.symbol: p.side for p in j.proposals()}
        j.close()
        assert sides.get("DNCO") == "sell_short" and sides.get("UPCO") == "buy"
        out = operations.execute(datetime(2026, 11, 20, 14, 36, tzinfo=UTC), tmp_path, cfg, fake=True)
        assert out["submitted"] >= 2
    j = operations._journal(tmp_path, cfg)
    dnco = j.positions()[next(p.instrument_id for p in j.proposals() if p.symbol == "DNCO")]
    assert dnco < 0
    short_value = -dnco * next(f["price"] for f in j.fills() if f["side"] == "sell")
    assert short_value / 100_000 <= 0.03 + 1e-9
    j.close()


def test_without_the_change_no_short_is_even_proposed(tmp_path):
    from candleisgreen import operations
    from tests.phase1_env import build_env, risk_service

    env = build_env(tmp_path, "auto_simulation")
    env.store.close()
    env.journal.close()
    with risk_service(tmp_path / "risk") as (risk, _):
        cfg = env.cfg.model_copy(update={"execution": env.cfg.execution.model_copy(update={"risk_service_url": risk.base_url})})
        operations.decide(datetime(2026, 11, 19, 21, 31, tzinfo=UTC), tmp_path, cfg, fake=True)
    j = operations._journal(tmp_path, cfg)
    assert all(p.side != "sell_short" for p in j.proposals())
    j.close()
