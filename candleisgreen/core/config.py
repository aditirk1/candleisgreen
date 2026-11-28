"""Versioned configuration. Every threshold and limit in the spec lives here, not in code.

The YAML file is validated against these models. Unknown keys are rejected. The loaded
config carries a content hash that every run and audit record can reference.
"""
from __future__ import annotations

from datetime import date
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
    preopen_check_local: str


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
    max_gross_leverage: float = Field(gt=0)
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
    shadow_min_turnover: float = Field(gt=0)


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
    min_history_days: int = Field(gt=1)
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
    # Short selling. Zero turns it off. Gross exposure above 1 would mean borrowing to trade.
    max_short_position_pct_equity: float = Field(ge=0, le=1)
    max_short_exposure_pct_equity: float = Field(ge=0, le=1)
    max_gross_exposure_pct_equity: float = Field(gt=0, le=1)
    execution_grade_feeds: tuple[str, ...] = Field(min_length=1)


class ClusteringConfig(_Section):
    """Correlation clusters for the cluster limit (Q7). All provisional."""

    lookback_days: int = Field(gt=20)
    min_observations: int = Field(gt=20)
    max_distance: float = Field(gt=0, le=1)
    min_stability: float = Field(ge=-1, le=1)
    refresh_days: int = Field(gt=0)


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
    risk_service_url: str

    @model_validator(mode="after")
    def _live_is_never_enabled(self) -> "ExecutionConfig":
        if self.live_trading_enabled:
            raise ValueError("live trading is not built in this project and cannot be enabled")
        return self


class AlpacaSourceConfig(_Section):
    trading_base_url: str
    data_base_url: str
    bars_feed: Literal["sip", "iex"]
    sip_delay_minutes: int = Field(ge=0)
    adjustment: Literal["raw"]
    symbols_per_request: int = Field(gt=0)
    request_timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)


class RecorderConfig(_Section):
    run_time_local: str
    close_time_local: str
    heartbeat_max_age_hours: float = Field(gt=0)


class SecSourceConfig(_Section):
    managers_13f: tuple[str, ...] = ()
    data_base_url: str
    tickers_url: str
    archives_base_url: str
    max_requests_per_second: float = Field(gt=0)
    user_agent_env: str
    filed_date_fallback_time_local: str
    concepts: tuple[str, ...]


class FredSeriesConfig(_Section):
    id: str
    license: str


class FredSourceConfig(_Section):
    base_url: str
    api_key_env: str
    release_time_local: str
    series: tuple[FredSeriesConfig, ...]


class TrialsSourceConfig(_Section):
    base_url: str
    page_size: int = Field(gt=0, le=1000)
    license: str


class SourcesConfig(_Section):
    alpaca: AlpacaSourceConfig
    recorder: RecorderConfig
    sec: SecSourceConfig
    fred: FredSourceConfig
    trials: TrialsSourceConfig


class TsMomentumConfig(_Section):
    lookback_days: int = Field(gt=0)
    skip_days: int = Field(ge=0)
    clip: float = Field(gt=0)


class ModelsConfig(_Section):
    ts_momentum: TsMomentumConfig


class SizingConfig(_Section):
    target_weight_per_name: float = Field(gt=0, le=1)
    max_names: int = Field(gt=0)
    max_short_names: int = Field(ge=0)
    min_trade_value_usd: float = Field(ge=0)


class ReproductionConfig(_Section):
    min_fraction_of_paper: float = Field(gt=0, le=1)
    interval_z: float = Field(gt=0)


class CriteriaConfig(_Section):
    new_factor_min_t: float = Field(gt=0)
    fdr_level: float = Field(gt=0, lt=1)
    forecast_significance: float = Field(gt=0, lt=1)
    forecast_subperiods: int = Field(gt=1)
    forecast_min_subperiods_passed: int = Field(gt=0)
    event_significance: float = Field(gt=0, lt=1)
    practitioner_min_claims: int = Field(gt=0)
    practitioner_interval_level: float = Field(gt=0, lt=1)
    novelty_similarity: float = Field(gt=0, le=1)


class InboxConfig(_Section):
    auto_fetch_hosts: tuple[str, ...] = ()
    summary_max_chars: int = Field(gt=0)
    max_file_bytes: int = Field(gt=0)


class ResearchConfig(_Section):
    inbox: InboxConfig
    lab_holdout_fraction: float = Field(gt=0, lt=1)
    reproduction: ReproductionConfig
    criteria: CriteriaConfig
    default_half_spread: float = Field(ge=0)
    monthly_hac_lag: int = Field(ge=0)
    osap_release: str


class FeedConfig(_Section):
    name: str
    url: str
    license: str


class NewsConfig(_Section):
    feeds: tuple[FeedConfig, ...]
    cluster_similarity: float = Field(gt=0, le=1)
    cluster_window_hours: float = Field(gt=0)
    live_view_hours: float = Field(gt=0)
    recent_view_days: float = Field(gt=0)
    max_summary_chars: int = Field(gt=0)


class MarketsConfig(_Section):
    us_exchanges: tuple[str, ...]
    sessions_utc: dict[str, str]


class CrisisEpisode(_Section):
    name: str
    start: date
    end: date


class TeachingConfig(_Section):
    review_intervals_days: tuple[int, ...]
    crises: tuple[CrisisEpisode, ...]


class OptionsRiskConfig(_Section):
    max_premium_pct_equity: float = Field(ge=0, le=1)
    max_total_premium_pct_equity: float = Field(ge=0, le=1)
    max_loss_pct_equity: float = Field(ge=0, le=1)
    min_days_to_expiry: int = Field(ge=0)
    max_spread_pct_of_mid: float = Field(gt=0)
    min_open_interest: int = Field(ge=0)
    allow_uncovered_short_calls: bool
    allow_uncovered_short_puts: bool
    require_cash_for_early_assignment: bool


class OptionsConfig(_Section):
    feed: str
    history_start: date
    history_end_delay_minutes: int = Field(ge=0)
    contract_multiplier: int = Field(gt=0)
    auto_exercise_threshold_usd: float = Field(ge=0)
    expiry_day_cutoff_local: str
    risk: OptionsRiskConfig


class CryptoRiskConfig(_Section):
    max_position_pct_equity: float = Field(ge=0, le=1)
    max_total_pct_equity: float = Field(ge=0, le=1)
    max_spread_bps: float = Field(gt=0)
    min_book_depth_usd: float = Field(ge=0)
    max_book_age_seconds: float = Field(gt=0)
    max_clock_skew_seconds: float = Field(ge=0)


class CryptoConfig(_Section):
    location: str
    symbols: tuple[str, ...]
    history_start: date
    day_boundary_utc: str
    fee_tiers: tuple[tuple[float, float, float], ...]
    max_order_notional_usd: float = Field(gt=0)
    risk: CryptoRiskConfig


class ForexRiskConfig(_Section):
    max_notional_pct_equity: float = Field(ge=0, le=1)
    max_gross_leverage: float = Field(gt=0, le=1)
    max_spread_pips: float = Field(gt=0)


class ForexConfig(_Section):
    practice_rest_url: str
    instruments: tuple[str, ...]
    granularity: str
    daily_alignment_hour: int = Field(ge=0, le=23)
    alignment_timezone: str
    max_candles_per_request: int = Field(gt=0)
    risk: ForexRiskConfig


class FuturesRiskConfig(_Section):
    max_margin_pct_equity: float = Field(ge=0, le=1)
    max_notional_pct_equity: float = Field(ge=0, le=1)


class FuturesConfig(_Section):
    cot_release_weekday_offset_days: int = Field(ge=0)
    cot_release_time_local: str
    cot_conservative_usable_days: int = Field(ge=0)
    cot_percentile_window_weeks: int = Field(gt=1)
    roll_business_days_before_last_trade: int = Field(ge=0)
    continuous_method: str
    risk: FuturesRiskConfig


class AssetsConfig(_Section):
    options: OptionsConfig
    crypto: CryptoConfig
    forex: ForexConfig
    futures: FuturesConfig

    @model_validator(mode="after")
    def _paper_or_practice_only(self) -> "AssetsConfig":
        if not self.forex.practice_rest_url.startswith("https://api-fxpractice."):
            raise ValueError("only the OANDA practice host is allowed")
        if self.futures.continuous_method not in ("back_adjusted", "ratio_adjusted", "unadjusted"):
            raise ValueError("unknown continuous futures method")
        return self


class AppConfig(_Section):
    config_version: str
    spec_version: str
    time: TimeConfig
    universe: UniverseConfig
    composite: CompositeConfig
    risk: RiskConfig
    clustering: ClusteringConfig
    execution: ExecutionConfig
    sources: SourcesConfig
    models: ModelsConfig
    sizing: SizingConfig
    research: ResearchConfig
    news: NewsConfig
    markets: MarketsConfig
    teaching: TeachingConfig
    assets: AssetsConfig

    @model_validator(mode="after")
    def _sizing_inside_hard_limits(self) -> "AppConfig":
        if self.sizing.target_weight_per_name > self.risk.hard_limits.max_position_pct_equity:
            raise ValueError("sizing.target_weight_per_name exceeds the hard position limit")
        if not self.sources.alpaca.trading_base_url.startswith("https://paper-api."):
            raise ValueError("only the Alpaca paper trading host is allowed")
        return self

    @property
    def config_hash(self) -> str:
        return sha256_hex(canonical_json(self.model_dump()))[:24]


def load_config(path: str | Path | None = None) -> AppConfig:
    with open(path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return AppConfig.model_validate(raw)
