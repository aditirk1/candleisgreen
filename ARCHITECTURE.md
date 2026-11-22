# ARCHITECTURE.md

Source: `SPEC.md` v3.1. This file describes services, interfaces and config layout. Field-level schemas are in `DATA_DICTIONARY.md`. Risk rules are in `RISK_POLICY.md`. Model and signal records are in `MODEL_REGISTRY.md`.

Status words used here: **built** means the code exists and its test ran. **planned** means not written yet.

## 1. Services and data flow

```
                 ┌────────────┐   observations    ┌──────────────────────┐
 vendors, files  │ Collectors │ ────────────────> │ Point-in-time store  │
 (fixtures now)  │ sources/   │                   │ data/  DuckDB+Parquet│
                 └────────────┘                   └──────────┬───────────┘
                                                             │ as_of(decision_time)
                 ┌────────────────────┐   claim cards,       v
                 │ Research processor │   experiments  ┌─────────────┐
                 │ research/ (planned)│ ─────────────> │ Quant engine│
                 └────────────────────┘                │ models/     │
                                                       │ composite/  │
                                                       │ backtests/  │
                                                       └──────┬──────┘
                                                              │ Forecast, OrderIntent
                                                              v
   kill switch, approvals    ┌──────────────────────────────────────────┐
   ───────────────────────>  │ Risk service  risk/   (fails closed)     │
   from the workstation      │ evaluate(intent, context, limits)        │
                             └───────────────────┬──────────────────────┘
                                                 │ RiskDecision (approved only)
                                                 v
                             ┌──────────────────────────────────────────┐
                             │ Broker adapters  broker/                 │
                             │ InternalSimulator (built)                │
                             │ Alpaca paper (planned, Phase 2)          │
                             │ Live: not built. Every live route raises │
                             └───────────────────┬──────────────────────┘
                                                 │ BrokerAck, Fill
                                                 v
                             ┌──────────────────────────────────────────┐
                             │ Audit log  core/audit.py                 │
                             │ append-only, hash-chained, SQLite        │
                             └──────────────────────────────────────────┘
```

Rules that the layout enforces:

1. Data reaches models only through `PointInTimeStore.as_of(decision_time)`. Any other route must pass `assert_no_lookahead`, which raises `LookaheadError`.
2. An order exists only after `risk.engine.evaluate` returns `approved`. Broker adapters call `assert_approved` and refuse anything else.
3. The risk engine is a pure function. It holds no broker handle and writes no limits.
4. Nothing in `models/`, `composite/` or `research/` imports `broker/`. The only caller of a broker is the execution path in `pipeline.py`.
5. The Composite and models read limits from config and can never write them.
6. Every step writes an audit record before the next step runs.

## 1a. Data by purpose, zero subscriptions

Each purpose uses a genuinely free dataset built for it (spec principle 11).

| Purpose | Source | Enters as |
| --- | --- | --- |
| Historical factor research, US | Open Source Asset Pricing portfolio returns, Kenneth French library | Portfolio return series with each paper's sample period. Built from CRSP, which includes delisted stocks. Supports hypotheses, never certifies an implementation |
| Historical factor research, global | JKP Global Factor Data | Factor and portfolio returns, non-commercial licence |
| Daily US market data | Alpaca consolidated history, requested at least 15 minutes after the close | Observations in the point-in-time store |
| Forward stock-level record | The recorder: full Alpaca asset list with inactive assets, daily bars and corporate actions after each close | Observations with `collection_mode: live`, the instrument master and completeness flags. Survivorship-aware, complete only where the flags say so |
| Live quotes for risk checks | Alpaca real-time IEX feed | `Quote` objects |
| Filings and fundamentals | SEC EDGAR submissions and XBRL, using the filed date | Observations |
| Macro | FRED, ALFRED, BLS, BEA | Observations with vintages |
| News | Lawful RSS feeds | Planned, Phase 4 |
| Paper execution | Alpaca paper account | Broker adapter, planned for Phase 2 |
| Language models | Optional local open-weight model, off by default | Planned |

What is not available is listed in `config/capabilities.yaml` and loaded by `core/capabilities.py`. `require(name)` raises `CapabilityNotAvailableError` for a capability marked `not_available`.

Evidence moves in order. Academic portfolio returns support a hypothesis from the first day (Tiers 2 and 3). An executable approximation is then evaluated by the platform with realistic costs (Tier 4), and prospective validation on the forward record decides promotion (Tier 5).

## 2. Repository layout

```
SPEC.md  REVIEW.md  QUESTIONS.md  CLAUDE.md
ARCHITECTURE.md  DATA_DICTIONARY.md  RISK_POLICY.md  MODEL_REGISTRY.md
DECISIONS.md  TEST_RESULTS.md  HANDOFF.md  README.md
pyproject.toml  Makefile
config/
  default.yaml              all thresholds and limits, versioned
  capabilities.yaml         what is available, limited or not available, and why
  parameters.yaml           the basis of every value in default.yaml
  licenses.yaml             what each data license permits
candleisgreen/
  core/                     shared contracts (built)
    timeutil.py             UTC rules
    ids.py                  content-derived IDs
    config.py               typed config loader
    schemas.py              Observation, Forecast, OrderIntent, RiskContext, RiskDecision, Fill, BrokerAck
    audit.py                hash-chained audit log
    capabilities.py         capability map loader, NOT AVAILABLE labels
    parameters.py           parameter basis registry: empirical, safeguard, provisional, external fact
    licenses.py             license registry and trading-use check
  sources/                  collectors. fixtures.py is built
  data/                     pit_store.py is built
  research/                 claim cards, evidence graph, experiment registry (planned, Phase 3)
  models/                   fixture_baseline.py is a Phase 0 stub. Level A models are planned
  composite/                spec section C, built and tested on synthetic data. See HANDOFF.md
  backtests/                planned, Phase 1 and 3
  risk/                     engine.py is built
  broker/                   base.py and simulator.py are built
  pipeline.py               Phase 0 offline flow (built)
ui/                         planned, Phase 1
tests/                      pytest suite and fixtures
```

The spec lists `sources/`, `data/`, `research/`, `models/`, `composite/`, `backtests/`, `risk/`, `broker/` as directories. They live inside one package, `candleisgreen/`, so that names like `data` and `tests` do not collide with other libraries (see `DECISIONS.md` D-001).

## 3. Interfaces

Signatures are exact for built code.

### 3.1 Time (`core/timeutil.py`, built)

```python
ensure_utc(dt: datetime) -> datetime              # raises NaiveDatetimeError
to_micros(dt: datetime) -> int                    # int64 microseconds since epoch, UTC
from_micros(us: int) -> datetime
iso_utc(dt: datetime) -> str                      # "2026-11-16T21:30:00.000000Z"
local_to_utc(day: date, hhmm: str, tz: str) -> datetime   # raises InvalidLocalTimeError
utc_now() -> datetime                             # the only wall-clock read
```

UTC rules:
1. Every datetime at a contract boundary is timezone-aware and converted to UTC. Naive datetimes are rejected.
2. Stores hold int64 microseconds since the epoch in UTC.
3. Local market times use the IANA zone database. A local time that does not exist or occurs twice on a daylight-saving boundary is rejected.
4. Interface text shows 24-hour time with zone (14:32 ET) and ISO dates.

### 3.2 IDs (`core/ids.py`, built)

```python
canonical_json(payload) -> str     # sorted keys, UTC ISO datetimes, no NaN
make_id(prefix: str, payload) -> str   # prefix + "_" + first 24 hex of SHA-256
```

| Entity | Prefix | Hashed content |
| --- | --- | --- |
| Observation | `obs` | instrument_id, vendor, field, event_time, vintage, value, adjustment_method |
| Data snapshot | `snap` | sorted observation IDs |
| Feature snapshot | `feat` | feature names and values |
| Forecast | `fc` | every field except issued_at |
| Order intent | `ord` | every field except rationale. This is the stable client order ID |
| Risk decision | `risk` | every field |
| Fill | `fill` | client_order_id, fill_seq |
| Composite run | `crun` | as_of, universe_hash, config_hash, signal list (planned) |

### 3.3 Point-in-time store (`data/pit_store.py`, built)

```python
class PointInTimeStore:
    def __init__(self, path=":memory:")
    def add(self, observations) -> int            # append-only, returns new rows
    def as_of(self, decision_time) -> AsOfView
    def unsafe_all(self, instrument_id, field) -> list[Observation]   # audits and leak fixtures only
    def export_parquet(self, path) -> None
    def count(self) -> int

class AsOfView:
    decision_time: datetime
    def series(self, instrument_id, field) -> list[Observation]
        # rows with first_usable_at < decision_time, latest vintage per event_time

assert_no_lookahead(observations, decision_time) -> None   # raises LookaheadError
snapshot_id(observations) -> str
```

### 3.4 Collectors (`sources/`)

```python
collect_bars(payload: dict, ingested_at: datetime) -> list[Observation]   # fixtures.py, built
```

Planned collectors follow one shape: `collect(checkpoint) -> (observations, new_checkpoint)`, stateless, with a health record per run (`source`, `last_success_at`, `rows`, `error`).

### 3.5 Models (`models/`)

```python
issue_forecast(asset_id, inputs, decision_time, issued_at, ...) -> Forecast
```

Every model calls `assert_no_lookahead(inputs, decision_time)` before producing output and records `data_snapshot_id` and `feature_snapshot_id`.

### 3.6 Composite (`composite/`, built)

One module per step of spec section C. All are pure functions of arrays and config. The names below are the target interface. The built modules are `stats.py`, `standardize.py`, `research_portfolio.py`, `edge.py`, `eligibility.py`, `weights.py`, `riskmodel.py`, `combine.py`, `optimizer.py` and `run.py`. Read their signatures in the code. Where they differ from this list, the code is current.

```python
standardize.cross_sectional(raw, cfg, sectors=None) -> z          # C.2
standardize.time_series(raw_history, cfg) -> z
standardize.smooth(z_history, horizon, cfg) -> z
edge.estimate(evidence: list[Evidence]) -> EdgeEstimate           # C.4: mu_hat, variance, prob_positive
edge.family_prior(others_mean, others_se, cfg) -> (m_k, tau_k)
eligibility.is_eligible(signal_state, cfg) -> EligibilityResult   # C.5
weights.within_family(mu, cov, cfg) -> w                          # C.6
weights.across_families(family_returns, cfg) -> w
weights.apply_caps(w, families, cfg) -> (w, unallocated)
weights.limit_change(w_new, w_prev, cfg) -> w
combine.composite_score(z, w, g) -> S                             # C.7
combine.alpha(S, sigma, ic_mean, n_days, allocated, cfg) -> alpha
combine.calibration(realized, forecast_unshrunk, cfg) -> CalibrationResult
optimizer.solve(alpha, B, F, D, x0, costs, limits, cfg) -> OptimizerResult   # C.8
run.daily(inputs, cfg) -> CompositeRun                            # C.10 output contract
```

### 3.7 Risk (`risk/engine.py`, built)

```python
evaluate(intent: OrderIntent, ctx: RiskContext, limits: HardLimits) -> RiskDecision
evaluate_portfolio(weights, clusters, limits, sectors=None, sector_cap=None) -> tuple[str, ...]   # independent check of a target book, UNKNOWN sectors pooled
limits_hash(limits: HardLimits) -> str
CHECKS: tuple[(name, check_function), ...]     # each returns None or a reason string
```

In Phase 0 the engine runs in-process and is called through this one function, with messages that are plain data. Phase 1 moves it behind a process boundary (a local socket or HTTP on localhost) without changing the message types. Until then "separate process" is planned, not built.

### 3.8 Brokers (`broker/`)

```python
class BrokerAdapter(ABC):
    venue: Venue
    def submit(self, intent, decision, quote) -> BrokerAck
    def open_orders(self) -> tuple[str, ...]
    def positions(self) -> dict[str, float]

assert_approved(intent, decision) -> None       # raises RiskApprovalRequiredError
assert_paper_endpoint(url) -> None              # raises LiveTradingDisabledError
```

`InternalSimulator` is built. `AlpacaPaperAdapter` is planned for Phase 2 and must call `assert_paper_endpoint` on its base URL at construction. `LiveBroker` exists only so a test can prove the live route raises.

### 3.9 Audit (`core/audit.py`, built)

```python
class AuditLog:
    def append(*, event_type, entity_id, payload, actor, strategy_version, event_time, received_time) -> str
    def records() -> list[dict]
    def verify() -> int | None       # None when intact, else first bad sequence number
```

## 4. Config layout

Three registries sit beside the config. `parameters.yaml` classifies every value in `default.yaml` by basis, and a test fails if a value is unclassified. `licenses.yaml` says what each data license permits. `capabilities.yaml` says what the platform can and cannot do. `ParameterRegistry.assert_tunable(path)` refuses any experiment that tries to vary a safeguard or an external fact.

One file, `config/default.yaml`, validated by `core/config.py`. Unknown keys are rejected. `config_version` is bumped on every edit, and `AppConfig.config_hash` goes into every audit record.

```
config_version, spec_version
time:        market_timezone, decision_time_local, execution_window_start_local, execution_window_end_local
universe:    min_price, min_median_dollar_volume_20d, exit_min_price,
             exit_min_median_dollar_volume_20d, dollar_volume_window_days, exclude_leveraged_inverse_etfs
composite:
  standardize:        winsor_lower_pct, winsor_upper_pct, ts_std_window_days, ts_clip,
                      ema_halflife_fraction_of_horizon
  research_portfolio: vol_target_annual, research_nav_usd, newey_west_max_lag_days, trading_days_per_year
  costs:              sec_fee_per_million_usd_sold, finra_taf_per_share_sold, finra_taf_max_per_trade_usd,
                      borrow_rate_annual, vol_lookback_days, min_vol_history_days, long_only_quantile
  edge:               delta_us_published, delta_non_us_published, delta_other_published, omega_factor,
                      cold_start_tau_annual, tau_floor_annual, family_min_signals_for_prior,
                      delta_replace_min_signals
  eligibility:        min_tier, capital_min_tier, min_prob_positive, min_oos_days, min_events, interval_level,
                      cost_multiplier, bootstrap_block_days, bootstrap_resamples, replication_significance
  weights:            cov_window_days, cov_min_days, hrp_min_families, signal_cap, family_cap,
                      max_monthly_relative_change, max_monthly_absolute_change_floor,
                      new_signal_initial_weight_max, duplicate_correlation_threshold
  alpha:              ic_horizon_days, ic_shrink_days, alpha_clip_sigmas, calibration_slope_min,
                      calibration_slope_max, calibration_min_t
  optimizer:          n_factors, cov_window_days, impact_kappa, impact_kappa_floor, vol_target_annual,
                      sector_cap, no_trade_band, lambda_bisection_iterations, lambda_min, lambda_max,
                      specific_var_shrink, min_history_days, alpha_horizon_days
risk:
  hard_limits:  max_position_pct_equity, max_cluster_pct_equity, max_order_pct_adv20, max_spread_pct,
                daily_loss_stop_pct_equity, max_quote_age_seconds
  loosening_delay_hours
execution:   mode, live_trading_enabled (must be false), simulator_starting_equity_usd
```

Rules:
- A number that appears in the spec appears here and nowhere in code. Tests read limits from the loaded config.
- `execution.live_trading_enabled: true` fails validation. There is no `live` mode value.
- Secrets are never in this file. They come from environment variables: `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` (paper keys only, Phase 2).

## 5. Storage

| Store | Technology | Holds | Status |
| --- | --- | --- | --- |
| Analytical | DuckDB file, export to Parquet | observations, later features and forecasts | built for observations |
| Transactional | SQLite | audit log now. Approvals, journal and registries later | audit built |
| Raw documents | object storage, content hash per item | papers, captures | planned |

SQLite appends use `BEGIN IMMEDIATE`, so two processes cannot fork the hash chain.

## 6. Processes and scheduling (planned)

| Process | Runs | Talks to |
| --- | --- | --- |
| Collectors | APScheduler 3.x jobs, on Oracle Cloud Always Free with a local scheduled task as fallback. Every job is safe to rerun, catches up after a gap, writes a heartbeat and copies its data back to Aditi's computer | point-in-time store |
| Daily decision run | 16:30 ET | store, models, Composite |
| Pre-open check | 09:00 ET, cancel only | risk service |
| Execution slicer | 09:35 to 10:30 ET | risk service, broker adapter |
| Risk service | always on, separate process and OS user | reads limits, writes audit |
| Workstation API | FastAPI | reads everything, writes approvals and the kill switch to the risk service only |

## 7. Commands

```bash
make setup     # create .venv and install
make ci        # the CI command: every test
make phase0    # run the offline event and print its IDs
```
