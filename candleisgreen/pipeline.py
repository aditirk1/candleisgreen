"""Phase 0 offline flow: one recorded event through every contract, with immutable IDs.

collector -> point-in-time store -> as-of view -> model -> order intent -> risk engine
-> internal simulator -> fill, with an audit record at every step.

Run: python -m candleisgreen.pipeline --fixture tests/fixtures/phase0_event.json --workdir var/phase0
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .broker.simulator import InternalSimulator
from .core.audit import AuditLog
from .core.config import AppConfig, load_config
from .core.schemas import Forecast, OrderIntent, Quote, RiskContext, RiskVerdict, Side, Venue
from .core.licenses import load_licenses
from .core.timeutil import ensure_utc, in_local_window, local_to_utc
from .data.pit_store import PointInTimeStore
from .models import fixture_baseline
from .risk.engine import evaluate
from .sources.fixtures import collect_bars, load_fixture

ACTOR = "system:pipeline"


class NotEligibleForOrdersError(RuntimeError):
    pass


def _ts(text: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))


def limit_price(side: Side, quote: Quote, offset_fraction: float) -> float:
    """Marketable limit: a share of the spread past the touch."""
    spread = quote.ask - quote.bid
    return quote.ask + offset_fraction * spread if side is Side.BUY else quote.bid - offset_fraction * spread


def build_intent(forecast: Forecast, quantity: float, session_date: str, venue: Venue,
                 limit: float) -> Optional[OrderIntent]:
    """Long-only limit orders. A non-positive signal gives no order."""
    if not forecast.eligible_for_orders:
        raise NotEligibleForOrdersError("forecast is not eligible for orders")
    if forecast.model_id == fixture_baseline.MODEL_ID and venue is not Venue.SIMULATION:
        raise NotEligibleForOrdersError("the fixture model may only be routed to the simulator")
    load_licenses().assert_use(forecast.data_licenses, "paper_trading")
    strength = forecast.signal_strength if forecast.signal_strength is not None else forecast.expected_excess_return
    if strength is None or strength <= 0 or quantity <= 0:
        return None
    return OrderIntent(
        forecast_id=forecast.forecast_id,
        asset_id=forecast.asset_id,
        side=Side.BUY,
        quantity=quantity,
        limit_price=limit,
        strategy_id=forecast.model_id,
        strategy_version=forecast.model_version,
        session_date=session_date,
        venue=venue,
        rationale=(
            f"{forecast.model_id} {forecast.model_version} signal strength {strength:+.2f}",
            f"Data snapshot {forecast.data_snapshot_id}",
            "SIMULATION order from the Phase 0 fixture flow",
        ),
    )


def run_offline_event(fixture_path: str | Path, workdir: str | Path, config: Optional[AppConfig] = None) -> dict:
    cfg = config or load_config()
    payload = load_fixture(fixture_path)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(work / "audit.sqlite")
    store = PointInTimeStore(work / "pit.duckdb")
    version = f"config:{cfg.config_version}:{cfg.config_hash}"

    def log(event_type: str, entity_id: str, body, when: datetime) -> None:
        audit.append(event_type=event_type, entity_id=entity_id, payload=body, actor=ACTOR,
                     strategy_version=version, event_time=when, received_time=when)

    try:
        # 1. Collect and store.
        ingested_at = _ts(payload["ingested_at"])
        observations = collect_bars(payload, ingested_at)
        store.add(observations)
        for obs in observations:
            log("observation_ingested", obs.observation_id, obs, ingested_at)

        # 2. Decide at the configured local decision time, using only what was usable then.
        decision_time = local_to_utc(
            date.fromisoformat(payload["decision_date"]), cfg.time.decision_time_local, cfg.time.market_timezone
        )
        asset = payload["asset_id"]
        closes = store.as_of(decision_time).series(asset, "close")
        forecast = fixture_baseline.issue_forecast(
            asset, closes, decision_time, issued_at=decision_time, horizon_days=int(payload["horizon_days"])
        )
        log("forecast_issued", forecast.forecast_id, forecast, decision_time)

        # 3. Size inside the hard limits, then ask the risk engine.
        ex = payload["execution"]
        now = _ts(ex["now"])
        quote = Quote(asset_id=asset, bid=ex["quote"]["bid"], ask=ex["quote"]["ask"],
                      quote_time=_ts(ex["quote"]["quote_time"]), feed=ex["quote"]["feed"])
        limits = cfg.risk.hard_limits
        by_position = limits.max_position_pct_equity * ex["equity"] / quote.ask
        by_volume = limits.max_order_pct_adv20 * ex["adv20_shares"]
        quantity = float(math.floor(ex["fraction_of_limit"] * min(by_position, by_volume)))
        limit = limit_price(Side.BUY, quote, cfg.execution.limit_offset_fraction)
        intent = build_intent(forecast, quantity, ex["session_date"], Venue.SIMULATION, limit)
        result = {
            "observation_ids": [o.observation_id for o in observations],
            "data_snapshot_id": forecast.data_snapshot_id,
            "forecast_id": forecast.forecast_id,
            "decision_time": decision_time.isoformat(),
            "client_order_id": None, "risk_decision_id": None, "risk_verdict": None,
            "risk_reasons": [], "fill_ids": [], "venue": Venue.SIMULATION.value,
        }
        if intent is None:
            log("no_order", forecast.forecast_id, {"reason": "signal not positive or zero size"}, now)
        else:
            log("order_intent_created", intent.client_order_id, intent, now)
            ctx = RiskContext(
                now=now, kill_switch_engaged=ex["kill_switch_engaged"], market_open=ex["market_open"],
                market_halted=ex["market_halted"], broker_connected=ex["broker_connected"],
                account_state_known=ex["account_state_known"],
                instrument_mapping_certain=ex["instrument_mapping_certain"], quote=quote,
                equity=ex["equity"], day_start_equity=ex["day_start_equity"],
                position_value=ex["position_value"], cluster_value=ex["cluster_value"],
                pending_position_value=ex["pending_position_value"],
                pending_cluster_value=ex["pending_cluster_value"],
                adv20_shares=ex["adv20_shares"],
                in_execution_window=in_local_window(
                    now, cfg.time.execution_window_start_local, cfg.time.execution_window_end_local,
                    cfg.time.market_timezone),
            )
            decision = evaluate(intent, ctx, limits)
            log("risk_decision", decision.risk_decision_id, decision, now)
            result.update(client_order_id=intent.client_order_id, risk_decision_id=decision.risk_decision_id,
                          risk_verdict=decision.verdict.value, risk_reasons=list(decision.reasons))
            if decision.verdict is RiskVerdict.APPROVED:
                broker = InternalSimulator(cfg.execution.simulator_starting_equity_usd)
                ack = broker.submit(intent, decision, quote)
                log("broker_ack", intent.client_order_id, ack, now)
                for fill in ack.fills:
                    log("fill", fill.fill_id, fill, fill.filled_at)
                result["fill_ids"] = [f.fill_id for f in ack.fills]
                result["slippage_bps"] = [round(f.slippage_bps, 4) for f in ack.fills]
                result["positions"] = broker.positions()
        result["audit_records"] = len(audit.records())
        result["audit_chain_ok"] = audit.verify() is None
        result["audit_head"] = audit.records()[-1]["record_hash"]
        return result
    finally:
        store.close()
        audit.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 0 offline event. SIMULATION only.")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    print(json.dumps(run_offline_event(args.fixture, args.workdir), indent=2))


if __name__ == "__main__":
    main()
