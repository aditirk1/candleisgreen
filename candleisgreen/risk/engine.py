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


def check_instrument_tag(intent, ctx, limits):
    """Only US-listed instruments tagged direct or proxy can receive orders. Everything else,
    every non-US instrument included, is research only."""
    if ctx.instrument_tag is None:
        return "instrument tag unknown"
    if ctx.instrument_tag not in ("direct", "proxy"):
        return f"instrument is {ctx.instrument_tag} and cannot receive orders"
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


def _effect(intent, ctx) -> Optional[str]:
    """What the order does to the position: increase_long, reduce_long, increase_short, reduce_short or flip.
    None when the current position is unknown."""
    if ctx.position_value is None:
        return None
    pos = ctx.position_value
    if intent.side is Side.BUY:
        return "reduce_short" if pos < -FLOAT_TOLERANCE else "increase_long"
    value = _order_value(intent, ctx)
    if pos > FLOAT_TOLERANCE:
        if value is not None and value > pos + FLOAT_TOLERANCE:
            return "flip"
        return "reduce_long"
    return "increase_short"


def _increases_risk(intent, ctx) -> bool:
    return _effect(intent, ctx) not in ("reduce_long", "reduce_short")


def check_daily_loss(intent, ctx, limits):
    if ctx.equity is None or ctx.day_start_equity is None or ctx.day_start_equity <= 0:
        return "daily loss cannot be evaluated"
    loss = (ctx.day_start_equity - ctx.equity) / ctx.day_start_equity
    if loss >= limits.daily_loss_stop_pct_equity and _increases_risk(intent, ctx):
        return f"daily loss stop hit, loss {loss:.2%}. Only orders that reduce risk are allowed"
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
    effect = _effect(intent, ctx)
    if effect == "flip":
        return "one order cannot turn a long position into a short one. Sell first, then short"
    if effect == "increase_long":
        after = ctx.position_value + ctx.pending_position_value + value
        if after / ctx.equity > limits.max_position_pct_equity:
            return f"position {after / ctx.equity:.2%} over limit {limits.max_position_pct_equity:.2%}"
    if effect == "increase_short":
        if limits.max_short_position_pct_equity <= 0:
            return "short selling is off [risk.hard_limits.max_short_position_pct_equity is 0]"
        if ctx.short_allowed is not True:
            return ("broker does not list it as shortable and easy to borrow" if ctx.short_allowed is False
                    else "borrow status unknown")
        if ctx.pending_short_position_value is None:
            return "pending short sales unknown"
        after = -ctx.position_value + ctx.pending_short_position_value + value
        if after / ctx.equity > limits.max_short_position_pct_equity:
            return f"short position {after / ctx.equity:.2%} over limit {limits.max_short_position_pct_equity:.2%}"
    return None


def check_exposure(intent, ctx, limits):
    """Whole-book limits for orders that add risk: gross exposure and total short exposure."""
    if not _increases_risk(intent, ctx):
        return None
    value = _order_value(intent, ctx)
    if value is None or not ctx.equity or ctx.gross_value is None or ctx.pending_gross_value is None:
        return "book exposure cannot be evaluated"
    gross = (ctx.gross_value + ctx.pending_gross_value + value) / ctx.equity
    if gross > limits.max_gross_exposure_pct_equity + FLOAT_TOLERANCE:
        return f"gross exposure {gross:.2%} over limit {limits.max_gross_exposure_pct_equity:.2%}"
    if _effect(intent, ctx) == "increase_short":
        if ctx.short_value is None or ctx.pending_short_value is None:
            return "short exposure cannot be evaluated"
        short = (ctx.short_value + ctx.pending_short_value + value) / ctx.equity
        if short > limits.max_short_exposure_pct_equity + FLOAT_TOLERANCE:
            return f"short exposure {short:.2%} over limit {limits.max_short_exposure_pct_equity:.2%}"
    return None


def check_cluster(intent, ctx, limits):
    """Gross value in the order's cluster, longs and shorts together, for orders that add risk."""
    value = _order_value(intent, ctx)
    if value is None or ctx.cluster_value is None or ctx.pending_cluster_value is None or not ctx.equity:
        return "cluster exposure cannot be evaluated"
    if _increases_risk(intent, ctx):
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
    ("instrument_tag", check_instrument_tag),
    ("quote_fresh", check_quote_fresh),
    ("quote_feed", check_quote_feed),
    ("limit_price", check_limit_price),
    ("spread", check_spread),
    ("daily_loss", check_daily_loss),
    ("position_size", check_position_size),
    ("exposure", check_exposure),
    ("cluster", check_cluster),
    ("order_vs_adv", check_order_vs_adv),
)


FLOAT_TOLERANCE = 1e-9  # numeric round-off only, not a risk threshold


UNKNOWN_GROUP = "UNKNOWN"


def evaluate_portfolio(weights: dict[str, float], clusters: dict[str, str], limits: HardLimits,
                       sectors: Optional[dict[str, Optional[str]]] = None,
                       sector_cap: Optional[float] = None) -> tuple[str, ...]:
    """Independent check of a proposed target book. Returns reasons, empty when it passes.

    This runs before any order is built from the optimizer's output. A name with no
    cluster mapping blocks the book. Sector and cluster limits are checked separately, so
    a name counts in both and neither classification can be used to bypass the other.
    Names with a missing or blank sector share one UNKNOWN bucket under the same cap.
    """
    reasons: list[str] = []
    if any(w != w for w in weights.values()):
        return ("target weights contain a non-number",)
    shorts = {a: -w for a, w in weights.items() if w < -FLOAT_TOLERANCE}
    if shorts and limits.max_short_position_pct_equity <= 0:
        reasons.append("short position in target book while short selling is off")
    gross = sum(abs(w) for w in weights.values())
    if gross > limits.max_gross_exposure_pct_equity + FLOAT_TOLERANCE:
        reasons.append(f"target book gross exposure {gross:.2%} over limit {limits.max_gross_exposure_pct_equity:.2%}")
    if sum(shorts.values()) > limits.max_short_exposure_pct_equity + FLOAT_TOLERANCE and limits.max_short_position_pct_equity > 0:
        reasons.append(f"target book short exposure {sum(shorts.values()):.2%} over limit {limits.max_short_exposure_pct_equity:.2%}")
    for asset, weight in weights.items():
        if weight > limits.max_position_pct_equity + FLOAT_TOLERANCE:
            reasons.append(f"{asset} at {weight:.2%} over position limit {limits.max_position_pct_equity:.2%}")
        if limits.max_short_position_pct_equity > 0 and -weight > limits.max_short_position_pct_equity + FLOAT_TOLERANCE:
            reasons.append(f"{asset} short {-weight:.2%} over limit {limits.max_short_position_pct_equity:.2%}")
    totals: dict[str, float] = {}
    for asset, weight in weights.items():
        if asset not in clusters:
            reasons.append(f"{asset} has no cluster mapping")
            continue
        totals[clusters[asset]] = totals.get(clusters[asset], 0.0) + abs(weight)
    for cluster, total in totals.items():
        if total > limits.max_cluster_pct_equity + FLOAT_TOLERANCE:
            reasons.append(f"cluster {cluster} at {total:.2%} over limit {limits.max_cluster_pct_equity:.2%}")
    if sectors is not None:
        if sector_cap is None:
            reasons.append("sector cap not supplied")
        else:
            by_sector: dict[str, float] = {}
            for asset, weight in weights.items():
                label = (sectors.get(asset) or "").strip() or UNKNOWN_GROUP
                by_sector[label] = by_sector.get(label, 0.0) + abs(weight)
            for sector, total in by_sector.items():
                if total > sector_cap + FLOAT_TOLERANCE:
                    reasons.append(f"sector {sector} at {total:.2%} over cap {sector_cap:.2%}")
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
