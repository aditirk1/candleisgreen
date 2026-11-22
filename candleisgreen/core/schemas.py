"""Typed contracts shared by every service. All models are immutable.

Field lists follow the spec sections "Data contract and point-in-time store" and
"Forecast contract". IDs are derived from content, see `ids.py`.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ids import make_id
from .timeutil import ensure_utc


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _all_datetimes_are_utc(cls, value):
        if isinstance(value, datetime):
            return ensure_utc(value)
        return value


class CollectionMode(str, Enum):
    LIVE = "live"
    BACKFILL = "backfill"


class Observation(Contract):
    """One point-in-time value. `first_usable_at` is the only time models may filter on."""

    instrument_id: str
    vendor: str
    raw_symbol: str
    exchange: str
    field: str
    value: Optional[float]
    event_time: datetime
    published_at: datetime
    vendor_available_at: datetime
    ingested_at: datetime
    first_usable_at: datetime
    timezone: str
    currency: str
    adjustment_method: str
    vintage: int = Field(ge=0)
    missing_flag: bool
    license: str
    collection_mode: CollectionMode

    @model_validator(mode="after")
    def _availability_is_consistent(self) -> "Observation":
        floor = max(self.event_time, self.published_at, self.vendor_available_at)
        if self.collection_mode is CollectionMode.LIVE:
            floor = max(floor, self.ingested_at)
        if self.first_usable_at < floor:
            raise ValueError("first_usable_at is earlier than the value could have been known")
        if self.missing_flag != (self.value is None):
            raise ValueError("missing_flag must be true exactly when value is null")
        return self

    @property
    def observation_id(self) -> str:
        return make_id(
            "obs",
            {
                "instrument_id": self.instrument_id,
                "vendor": self.vendor,
                "field": self.field,
                "event_time": self.event_time,
                "vintage": self.vintage,
                "value": self.value,
                "adjustment_method": self.adjustment_method,
            },
        )


class CalibrationStatus(str, Enum):
    CALIBRATED = "calibrated"
    SIGNAL_STRENGTH_ONLY = "signal_strength_only"
    NOT_AVAILABLE = "not_available"


class RecordType(str, Enum):
    """Prospective: issued before the outcome window started. Retrospective: reconstructed
    later by walk-forward, even with point-in-time inputs. The two are never pooled."""

    PROSPECTIVE = "prospective"
    RETROSPECTIVE = "retrospective"


class Forecast(Contract):
    model_id: str
    model_version: str
    asset_id: str
    issued_at: datetime
    as_of: datetime
    target_definition: str
    target_start: datetime
    target_end: datetime
    expected_excess_return: Optional[float] = None
    signal_strength: Optional[float] = None
    quantiles: Optional[dict[str, float]] = None
    training_cutoff: datetime
    data_snapshot_id: str
    feature_snapshot_id: str
    calibration_status: CalibrationStatus
    evidence_refs: tuple[str, ...] = ()
    eligible_for_orders: bool
    record_type: RecordType = RecordType.PROSPECTIVE
    data_licenses: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _one_output(self) -> "Forecast":
        if (self.expected_excess_return is None) == (self.signal_strength is None):
            raise ValueError("set exactly one of expected_excess_return or signal_strength")
        if self.expected_excess_return is not None and self.calibration_status is not CalibrationStatus.CALIBRATED:
            raise ValueError("expected_excess_return requires calibration_status calibrated")
        if self.quantiles is not None and self.calibration_status is not CalibrationStatus.CALIBRATED:
            raise ValueError("quantiles require calibration_status calibrated")
        if self.training_cutoff > self.as_of or self.as_of > self.issued_at:
            raise ValueError("require training_cutoff <= as_of <= issued_at")
        if self.target_start < self.as_of or self.target_end <= self.target_start:
            raise ValueError("target window must start at or after as_of and have positive length")
        if self.record_type is RecordType.PROSPECTIVE and self.issued_at > self.target_start:
            raise ValueError("a forecast issued after its target window started is retrospective")
        if self.record_type is RecordType.RETROSPECTIVE and self.eligible_for_orders:
            raise ValueError("a retrospective forecast can never be eligible for orders")
        return self

    @property
    def forecast_id(self) -> str:
        return make_id("fc", self.model_dump(exclude={"issued_at"}))


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Venue(str, Enum):
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"


class OrderIntent(Contract):
    """A proposed order. It is not an order until the risk service approves it."""

    forecast_id: str
    asset_id: str
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    strategy_id: str
    strategy_version: str
    session_date: str
    venue: Venue
    rationale: tuple[str, ...] = ()

    @field_validator("rationale")
    @classmethod
    def _rationale_is_short(cls, value):
        if len(value) > 6:
            raise ValueError("a trade rationale is at most six short lines")
        return value

    @property
    def client_order_id(self) -> str:
        """Stable across retries, so an uncertain broker response never causes a duplicate."""
        return make_id("ord", self.model_dump(exclude={"rationale"}))


class Quote(Contract):
    asset_id: str
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    quote_time: datetime
    feed: str  # for example iex_realtime, sip_delayed, fixture_realtime
    bid_size: Optional[float] = Field(default=None, ge=0)
    ask_size: Optional[float] = Field(default=None, ge=0)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class RiskContext(Contract):
    """Everything the risk service needs. A missing value means the rule cannot be evaluated."""

    now: datetime
    kill_switch_engaged: Optional[bool] = None
    market_open: Optional[bool] = None
    market_halted: Optional[bool] = None
    broker_connected: Optional[bool] = None
    account_state_known: Optional[bool] = None
    instrument_mapping_certain: Optional[bool] = None
    quote: Optional[Quote] = None
    equity: Optional[float] = None
    day_start_equity: Optional[float] = None
    position_value: Optional[float] = None
    cluster_value: Optional[float] = None
    pending_position_value: Optional[float] = None  # open buy orders in this instrument
    pending_cluster_value: Optional[float] = None  # open buy orders in its cluster
    adv20_shares: Optional[float] = None
    in_execution_window: Optional[bool] = None


class RiskVerdict(str, Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"


class RiskDecision(Contract):
    client_order_id: str
    verdict: RiskVerdict
    reasons: tuple[str, ...]
    checks_run: tuple[str, ...]
    limits_hash: str
    decided_at: datetime

    @property
    def risk_decision_id(self) -> str:
        return make_id("risk", self.model_dump())


class Fill(Contract):
    client_order_id: str
    asset_id: str
    side: Side
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    venue: Venue
    filled_at: datetime
    fill_seq: int = Field(ge=0)
    arrival_mid: Optional[float] = Field(default=None, gt=0)  # mid quote when the order was sent

    @property
    def slippage_bps(self) -> Optional[float]:
        """Cost against the arrival mid, positive when the fill was worse."""
        if self.arrival_mid is None:
            return None
        sign = 1 if self.side is Side.BUY else -1
        return sign * (self.price - self.arrival_mid) / self.arrival_mid * 1e4

    @property
    def fill_id(self) -> str:
        return make_id("fill", {"client_order_id": self.client_order_id, "fill_seq": self.fill_seq})


OrderStatus = Literal["accepted", "filled", "partially_filled", "rejected", "unknown"]


class BrokerAck(Contract):
    client_order_id: str
    status: OrderStatus
    venue: Venue
    fills: tuple[Fill, ...] = ()
    message: str = ""
