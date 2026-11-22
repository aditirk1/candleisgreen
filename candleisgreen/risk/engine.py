"""Risk engine. Checks every order intent against the hard limits and fails closed.

Design rules:
1. The engine is a pure function of (intent, context, limits). It holds no broker handle
   and cannot place, change or cancel an order.
2. A missing input means the rule cannot be evaluated, and the order is blocked.
3. Any exception inside a check blocks the order.
4. The engine reads limits. Nothing in this module writes them.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..core.config import HardLimits
from ..core.ids import canonical_json, sha256_hex
from ..core.schemas import OrderIntent, RiskContext, RiskDecision, RiskVerdict, Side, Venue

Check = Callable[[OrderIntent, RiskContext, HardLimits], Optional[str]]


def _require_true(value: Optional[bool], unknown: str, false: str) -> Optional[str]:
    if value is None:
        return unknown
    return None if value else false


def check_venue(intent, ctx, limits):
    if intent.venue not in (Venue.SIMULATION, Venue.PAPER):
        return "venue is not SIMULATION or PAPER"
    return None


def check_kill_switch(intent, ctx, limits):
    if ctx.kill_switch_engaged is None:
        return "kill switch state unknown"
    return "kill switch engaged" if ctx.kill_switch_engaged else None


def check_market_open(intent, ctx, limits):
    reason = _require_true(ctx.market_open, "market session unknown", "market closed")
    if reason:
        return reason
    if ctx.market_halted is None:
        return "halt state unknown"
    return "market or instrument halted" if ctx.market_halted else None


def check_broker(intent, ctx, limits):
    return _require_true(ctx.broker_connected, "broker connection unknown", "broker disconnected")


def check_account(intent, ctx, limits):
    reason = _require_true(ctx.account_state_known, "account state unknown", "account state unknown")
    if reason:
        return reason
    if ctx.equity is None or ctx.equity <= 0:
        return "equity unknown or not positive"
    return None


def check_instrument(intent, ctx, limits):
    return _require_true(
        ctx.instrument_mapping_certain, "instrument mapping unknown", "instrument mapping uncertain"
    )


def check_execution_window(intent, ctx, limits):
    return _require_true(ctx.in_execution_window, "execution window unknown", "outside the execution window")


def check_quote_feed(intent, ctx, limits):
    """Only execution-grade feeds may price an order. Delayed consolidated data never is."""
    if ctx.quote is None:
        return "no quote"
    if ctx.quote.feed not in limits.execution_grade_feeds:
        return f"quote feed '{ctx.quote.feed}' is not execution grade"
    if ctx.quote.bid_size == 0 or ctx.quote.ask_size == 0:
        return "quote has no size on one side"
    return None


def check_limit_price(intent, ctx, limits):
    """Limit orders only. The limit may not reach further than the spread limit from mid."""
    if ctx.quote is None:
        return "no quote"
    mid = ctx.quote.mid
    if intent.side is Side.BUY and intent.limit_price > mid * (1 + limits.max_spread_pct):
        return f"buy limit {intent.limit_price:.4f} too far above mid {mid:.4f}"
    if intent.side is Side.SELL and intent.limit_price < mid * (1 - limits.max_spread_pct):
        return f"sell limit {intent.limit_price:.4f} too far below mid {mid:.4f}"
    return None


def check_quote_fresh(intent, ctx, limits):
    if ctx.quote is None:
        return "no quote"
    if ctx.quote.asset_id != intent.asset_id:
        return "quote is for a different instrument"
    age = (ctx.now - ctx.quote.quote_time).total_seconds()
    if age < 0:
        return "quote time is in the future"
    if age > limits.max_quote_age_seconds:
        return f"stale quote, age {age:.1f} s over limit {limits.max_quote_age_seconds:g} s"
    return None


def check_spread(intent, ctx, limits):
    if ctx.quote is None:
        return "no quote"
    if ctx.quote.ask < ctx.quote.bid:
        return "crossed quote"
    mid = (ctx.quote.ask + ctx.quote.bid) / 2
    spread = (ctx.quote.ask - ctx.quote.bid) / mid
    if spread > limits.max_spread_pct:
        return f"spread {spread:.4%} over limit {limits.max_spread_pct:.4%}"
    return None


def check_daily_loss(intent, ctx, limits):
    if ctx.equity is None or ctx.day_start_equity is None or ctx.day_start_equity <= 0:
        return "daily loss cannot be evaluated"
    loss = (ctx.day_start_equity - ctx.equity) / ctx.day_start_equity
    if loss >= limits.daily_loss_stop_pct_equity and intent.side is Side.BUY:
        return f"daily loss stop hit, loss {loss:.2%}"
    return None


def _order_value(intent: OrderIntent, ctx: RiskContext) -> Optional[float]:
    if ctx.quote is None:
        return None
    price = ctx.quote.ask if intent.side is Side.BUY else ctx.quote.bid
    return intent.quantity * price


def check_position_size(intent, ctx, limits):
    value = _order_value(intent, ctx)
    if value is None or ctx.position_value is None or ctx.pending_position_value is None or not ctx.equity:
        return "position size cannot be evaluated"
    sign = 1 if intent.side is Side.BUY else -1
    after = ctx.position_value + (ctx.pending_position_value if sign > 0 else 0.0) + sign * value
    if after < -1e-9:
        return "order would create a short position"
    if sign > 0 and after / ctx.equity > limits.max_position_pct_equity:
        return f"position {after / ctx.equity:.2%} over limit {limits.max_position_pct_equity:.2%}"
    return None


def check_cluster(intent, ctx, limits):
    value = _order_value(intent, ctx)
    if value is None or ctx.cluster_value is None or ctx.pending_cluster_value is None or not ctx.equity:
        return "cluster exposure cannot be evaluated"
    if intent.side is Side.BUY:
        after = (ctx.cluster_value + ctx.pending_cluster_value + value) / ctx.equity
        if after > limits.max_cluster_pct_equity:
            return f"cluster {after:.2%} over limit {limits.max_cluster_pct_equity:.2%}"
    return None


def check_order_vs_adv(intent, ctx, limits):
    if ctx.adv20_shares is None or ctx.adv20_shares <= 0:
        return "average daily volume unknown"
    share = intent.quantity / ctx.adv20_shares
    if share > limits.max_order_pct_adv20:
        return f"order {share:.3%} of ADV over limit {limits.max_order_pct_adv20:.3%}"
    return None


CHECKS: tuple[tuple[str, Check], ...] = (
    ("venue", check_venue),
    ("kill_switch", check_kill_switch),
    ("market_open", check_market_open),
    ("execution_window", check_execution_window),
    ("broker", check_broker),
    ("account", check_account),
    ("instrument", check_instrument),
    ("quote_fresh", check_quote_fresh),
    ("quote_feed", check_quote_feed),
    ("limit_price", check_limit_price),
    ("spread", check_spread),
    ("daily_loss", check_daily_loss),
    ("position_size", check_position_size),
    ("cluster", check_cluster),
    ("order_vs_adv", check_order_vs_adv),
)


FLOAT_TOLERANCE = 1e-9  # numeric round-off only, not a risk threshold


def evaluate_portfolio(weights: dict[str, float], clusters: dict[str, str], limits: HardLimits) -> tuple[str, ...]:
    """Independent check of a proposed target book. Returns reasons, empty when it passes.

    This runs before any order is built from the optimizer's output. A name with no
    cluster mapping blocks the book.
    """
    reasons: list[str] = []
    if any(w != w for w in weights.values()):
        return ("target weights contain a non-number",)
    if any(w < -FLOAT_TOLERANCE for w in weights.values()):
        reasons.append("short position in target book")
    if sum(weights.values()) > 1.0 + FLOAT_TOLERANCE:
        reasons.append("target book uses leverage")
    for asset, weight in weights.items():
        if weight > limits.max_position_pct_equity + FLOAT_TOLERANCE:
            reasons.append(f"{asset} at {weight:.2%} over position limit {limits.max_position_pct_equity:.2%}")
    totals: dict[str, float] = {}
    for asset, weight in weights.items():
        if asset not in clusters:
            reasons.append(f"{asset} has no cluster mapping")
            continue
        totals[clusters[asset]] = totals.get(clusters[asset], 0.0) + weight
    for cluster, total in totals.items():
        if total > limits.max_cluster_pct_equity + FLOAT_TOLERANCE:
            reasons.append(f"cluster {cluster} at {total:.2%} over limit {limits.max_cluster_pct_equity:.2%}")
    return tuple(reasons)


def limits_hash(limits: HardLimits) -> str:
    return sha256_hex(canonical_json(limits.model_dump()))[:24]


def evaluate(intent: OrderIntent, ctx: RiskContext, limits: HardLimits) -> RiskDecision:
    """Run every check. Approve only when all of them pass."""
    reasons: list[str] = []
    names: list[str] = []
    for name, check in CHECKS:
        names.append(name)
        try:
            reason = check(intent, ctx, limits)
        except Exception as exc:  # fail closed on anything unexpected
            reason = f"rule could not be evaluated ({type(exc).__name__})"
        if reason:
            reasons.append(f"{name}: {reason}")
    return RiskDecision(
        client_order_id=intent.client_order_id,
        verdict=RiskVerdict.BLOCKED if reasons else RiskVerdict.APPROVED,
        reasons=tuple(reasons),
        checks_run=tuple(names),
        limits_hash=limits_hash(limits),
        decided_at=ctx.now,
    )
