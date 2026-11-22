from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.core.schemas import (
    CollectionMode, Observation, OrderIntent, Quote, RiskContext, Side, Venue,
)

FIXTURE = Path(__file__).parent / "fixtures" / "phase0_event.json"
T0 = datetime(2026, 11, 16, 14, 40, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def limits(cfg):
    return cfg.risk.hard_limits


def make_obs(value=50.0, event=None, usable=None, vintage=0, field="close", instrument="inst_TEST"):
    event = event or datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc)
    usable = usable or event + timedelta(minutes=15)
    return Observation(
        instrument_id=instrument, vendor="fixture", raw_symbol="TEST", exchange="XNYS", field=field,
        value=value, event_time=event, published_at=event, vendor_available_at=event,
        ingested_at=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc), first_usable_at=usable,
        timezone="America/New_York", currency="USD", adjustment_method="none", vintage=vintage,
        missing_flag=value is None, license="synthetic", collection_mode=CollectionMode.BACKFILL,
    )


def make_intent(quantity=48.0, side=Side.BUY, venue=Venue.SIMULATION, limit=None):
    limit = limit if limit is not None else (51.24 if side is Side.BUY else 51.16)
    return OrderIntent(
        forecast_id="fc_test", asset_id="inst_TEST", side=side, quantity=quantity, limit_price=limit,
        strategy_id="fixture_baseline", strategy_version="0.1.0", session_date="2026-11-16", venue=venue,
    )


def make_ctx(**overrides):
    base = dict(
        now=T0, kill_switch_engaged=False, market_open=True, market_halted=False, broker_connected=True,
        account_state_known=True, instrument_mapping_certain=True,
        quote=Quote(asset_id="inst_TEST", bid=51.18, ask=51.22, quote_time=T0 - timedelta(seconds=3),
                    feed="iex_realtime"),
        equity=100_000.0, day_start_equity=100_000.0, position_value=0.0, cluster_value=0.0,
        pending_position_value=0.0, pending_cluster_value=0.0, adv20_shares=2_000_000.0,
        in_execution_window=True,
    )
    base.update(overrides)
    return RiskContext(**base)
