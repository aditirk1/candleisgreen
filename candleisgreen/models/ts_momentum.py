"""Level A baseline: time-series momentum (spec Model laboratory, MODEL_REGISTRY ts_momentum_252_21).

Score = log return from t - lookback to t - skip, divided by its realized volatility over
the same window, clipped. Positive means the trend is up. The output is `signal_strength`
only, because the model is not calibrated. It holds no evidence tier yet.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np

from ..core.config import TsMomentumConfig
from ..core.ids import make_id
from ..core.schemas import CalibrationStatus, Forecast, Observation
from ..data.pit_store import assert_no_lookahead, snapshot_id

MODEL_ID = "ts_momentum_252_21"
MODEL_VERSION = "1.0.0"


def score(adjusted_closes: Sequence[float], cfg: TsMomentumConfig) -> Optional[float]:
    closes = np.asarray(adjusted_closes, dtype=float)
    need = cfg.lookback_days + 1
    if closes.size < need or (closes[-need:] <= 0).any():
        return None
    window = closes[-need: closes.size - cfg.skip_days] if cfg.skip_days else closes[-need:]
    rets = np.diff(np.log(window))
    if rets.size < 2:
        return None
    vol = rets.std(ddof=1)
    if not vol > 0:
        return None
    raw = rets.sum() / (vol * math.sqrt(rets.size))
    return float(np.clip(raw, -cfg.clip, cfg.clip))


def issue_forecast(asset_id: str, inputs: Sequence[Observation], adjusted: Sequence[float], decision_time: datetime,
                   issued_at: datetime, target_start: datetime, cfg: TsMomentumConfig,
                   licenses: Sequence[str]) -> Optional[Forecast]:
    assert_no_lookahead(inputs, decision_time)
    value = score(adjusted, cfg)
    if value is None:
        return None
    return Forecast(
        model_id=MODEL_ID, model_version=MODEL_VERSION, asset_id=asset_id, issued_at=issued_at, as_of=decision_time,
        target_definition=f"direction of the next {cfg.skip_days or 21} trading days of total return",
        target_start=target_start, target_end=target_start + timedelta(days=30), signal_strength=value,
        training_cutoff=decision_time, data_snapshot_id=snapshot_id(inputs),
        feature_snapshot_id=make_id("feat", {"ts_momentum": round(value, 12), "n": len(adjusted)}),
        calibration_status=CalibrationStatus.SIGNAL_STRENGTH_ONLY, eligible_for_orders=True,
        data_licenses=tuple(sorted(set(licenses))))
