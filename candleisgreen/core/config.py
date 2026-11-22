"""Versioned configuration. Every threshold and limit in the spec lives here, not in code.

The YAML file is validated against these models. Unknown keys are rejected. The loaded
config carries a content hash that every run and audit record can reference.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ids import canonical_json, sha256_hex

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TimeConfig(_Section):
    market_timezone: str
    decision_time_local: str
    execution_window_start_local: str
    execution_window_end_local: str


class ResearchUniverseConfig(_Section):
    """A research-only universe. It can never receive orders."""

    description: str
    min_price: float = Field(ge=0)
    min_median_dollar_volume_20d: float = Field(ge=0)
    sic_codes: tuple[int, ...] = ()


class UniverseConfig(_Section):
    min_price: float = Field(gt=0)
    min_median_dollar_volume_20d: float = Field(gt=0)
    exit_min_price: float = Field(gt=0)
    exit_min_median_dollar_volume_20d: float = Field(gt=0)
    dollar_volume_window_days: int = Field(gt=0)
    exclude_leveraged_inverse_etfs: bool
    research_universes: dict[str, ResearchUniverseConfig] = {}


class StandardizeConfig(_Section):
    winsor_lower_pct: float
    winsor_upper_pct: float
    ts_std_window_days: int
    ts_clip: float
    ema_halflife_fraction_of_horizon: float


class ResearchPortfolioConfig(_Section):
    vol_target_annual: float
    research_nav_usd: float
    newey_west_max_lag_days: int
    trading_days_per_year: int


class CostConfig(_Section):
    sec_fee_per_million_usd_sold: float = Field(ge=0)
    finra_taf_per_share_sold: float = Field(ge=0)
    finra_taf_max_per_trade_usd: float = Field(ge=0)
    borrow_rate_annual: float = Field(ge=0)
    vol_lookback_days: int = Field(gt=1)
    min_vol_history_days: int = Field(gt=1)
    long_only_quantile: float = Field(gt=0, lt=1)


class EdgeConfig(_Section):
    delta_us_published: float
    delta_non_us_published: float
    delta_other_published: float
    omega_factor: float
    cold_start_tau_annual: float
    tau_floor_annual: float
    family_min_signals_for_prior: int
    delta_replace_min_signals: int
    implementation_gap_factor: float = Field(ge=0)


class EligibilityConfig(_Section):
    min_tier: int
    capital_min_tier: int
    min_prob_positive: float
    min_oos_days: int
    min_events: int
    interval_level: float = Field(gt=0, lt=1)
    cost_multiplier: float = Field(ge=1)
    bootstrap_block_days: int = Field(gt=0)
    bootstrap_resamples: int = Field(gt=0)
    replication_significance: float = Field(gt=0, lt=1)


class PromotionConfig(_Section):
    """Tier 5 prospective validation. A strategy may declare stricter values."""

    shadow_min_trading_days: int = Field(gt=0)
    default_min_shadow_trades: int = Field(gt=0)
    default_max_se_to_expected_ratio: float = Field(gt=0)
    shadow_band_level: float = Field(gt=0, lt=1)
    max_tracking_error_annual: float = Field(gt=0)


class MonitoringConfig(_Section):
    """Strategy deterioration, measured against the forecast distribution."""

    min_observation_days: int = Field(gt=0)
    review_window_days: int = Field(gt=0)
    alert_probability: float = Field(gt=0, lt=1)


class WeightConfig(_Section):
    cov_window_days: int
    cov_min_days: int
    hrp_min_families: int
    signal_cap: float
    family_cap: float
    max_monthly_relative_change: float
    max_monthly_absolute_change_floor: float
    new_signal_initial_weight_max: float
    duplicate_correlation_threshold: float


class AlphaConfig(_Section):
    ic_horizon_days: int
    ic_shrink_days: int
    alpha_clip_sigmas: float
    calibration_slope_min: float
    calibration_slope_max: float
    calibration_min_t: float


class OptimizerConfig(_Section):
    n_factors: int
    cov_window_days: int
    impact_kappa: float
    impact_kappa_floor: float
    vol_target_annual: float
    sector_cap: float
    no_trade_band: float
    lambda_bisection_iterations: int
    lambda_min: float = Field(gt=0)
    lambda_max: float = Field(gt=0)
    specific_var_shrink: float = Field(ge=0, le=1)
    min_history_days: int
    alpha_horizon_days: int


class CompositeConfig(_Section):
    standardize: StandardizeConfig
    research_portfolio: ResearchPortfolioConfig
    costs: CostConfig
    edge: EdgeConfig
    eligibility: EligibilityConfig
    weights: WeightConfig
    promotion: PromotionConfig
    monitoring: MonitoringConfig
    alpha: AlphaConfig
    optimizer: OptimizerConfig


class HardLimits(_Section):
    """Hard risk limits. Aditi sets these. Code never changes them."""

    max_position_pct_equity: float = Field(gt=0, le=1)
    max_cluster_pct_equity: float = Field(gt=0, le=1)
    max_order_pct_adv20: float = Field(gt=0, le=1)
    max_spread_pct: float = Field(gt=0, le=1)
    daily_loss_stop_pct_equity: float = Field(gt=0, le=1)
    max_quote_age_seconds: float = Field(gt=0)
    execution_grade_feeds: tuple[str, ...] = Field(min_length=1)


class RiskConfig(_Section):
    hard_limits: HardLimits
    loosening_delay_hours: int = Field(ge=0)


Mode = Literal[
    "research",
    "teaching",
    "manual_simulation",
    "auto_simulation",
    "broker_paper_approval",
    "broker_paper_auto",
]


class ExecutionConfig(_Section):
    mode: Mode
    live_trading_enabled: bool
    simulator_starting_equity_usd: float = Field(gt=0)
    order_type: Literal["limit"]
    limit_offset_fraction: float = Field(ge=0)

    @model_validator(mode="after")
    def _live_is_never_enabled(self) -> "ExecutionConfig":
        if self.live_trading_enabled:
            raise ValueError("live trading is not built in this project and cannot be enabled")
        return self


class AppConfig(_Section):
    config_version: str
    spec_version: str
    time: TimeConfig
    universe: UniverseConfig
    composite: CompositeConfig
    risk: RiskConfig
    execution: ExecutionConfig

    @property
    def config_hash(self) -> str:
        return sha256_hex(canonical_json(self.model_dump()))[:24]


def load_config(path: str | Path | None = None) -> AppConfig:
    with open(path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return AppConfig.model_validate(raw)
