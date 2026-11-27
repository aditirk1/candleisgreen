"""Phase 0 stub model. It exists to push one event through every contract.

It is not a trading model and has no evidence tier. Its output is `signal_strength` only,
never an expected return, because nothing here is calibrated. Its forecasts may be routed
to the internal simulator only. The pipeline refuses to send them to a paper broker.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from ..core.ids import make_id
from ..core.schemas import CalibrationStatus, Forecast, Observation
from ..data.pit_store import assert_no_lookahead, snapshot_id

MODEL_ID = "fixture_baseline"
MODEL_VERSION = "0.1.0"


def last_change_sign(closes: Sequence[Observation]) -> float:
    values = [o.value for o in closes if o.value is not None]
    if len(values) < 2:
        return 0.0
    change = values[-1] - values[0]
    return 0.0 if change == 0 else (1.0 if change > 0 else -1.0)


def issue_forecast(
    asset_id: str,
    closes: Sequence[Observation],
    decision_time: datetime,
    issued_at: datetime,
    horizon_days: int,
) -> Forecast:
    """Build a forecast from inputs. Refuses any input not usable before decision time."""
    assert_no_lookahead(closes, decision_time)
    feature = last_change_sign(closes)
    return Forecast(
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        asset_id=asset_id,
        issued_at=issued_at,
        as_of=decision_time,
        target_definition=f"sign of close-to-close return over {horizon_days} calendar days",
        target_start=decision_time,
        target_end=decision_time + timedelta(days=horizon_days),
        signal_strength=feature,
        training_cutoff=decision_time,
        data_snapshot_id=snapshot_id(closes),
        feature_snapshot_id=make_id("feat", {"last_change_sign": feature, "n": len(closes)}),
        calibration_status=CalibrationStatus.SIGNAL_STRENGTH_ONLY,
        evidence_refs=(),
        eligible_for_orders=True,
        data_licenses=tuple(sorted({o.license for o in closes})),
    )
