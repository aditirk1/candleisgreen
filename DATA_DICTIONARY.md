# DATA_DICTIONARY.md

Source: `SPEC.md` v3.1. Schemas marked **built** are enforced in `candleisgreen/core/schemas.py` and tested. Schemas marked **planned** are the target and are not in code yet.

Conventions:
- All timestamps are UTC. In Python they are timezone-aware datetimes. In stores they are `BIGINT` microseconds since the epoch.
- All contract objects are immutable. A change is a new object with a new ID.
- IDs are content hashes (see `ARCHITECTURE.md` section 3.2).
- Money is in the instrument's currency unless the field name ends in `_usd`. Rates and weights are fractions, so 5% is 0.05.

## 1. Observation (built)

One point-in-time value. Table `observations` in DuckDB.

| Field | Type | Meaning |
| --- | --- | --- |
| `observation_id` | VARCHAR, primary key | `obs_` hash of instrument_id, vendor, field, event_time, vintage, value, adjustment_method |
| `instrument_id` | VARCHAR | Platform ID that survives ticker changes |
| `vendor` | VARCHAR | Data source name |
| `raw_symbol` | VARCHAR | Symbol as the vendor sent it |
| `exchange` | VARCHAR | ISO 10383 MIC, for example XNYS |
| `field` | VARCHAR | What is measured: `close`, `volume`, `eps`, and so on |
| `value` | DOUBLE, nullable | The number. Null only when `missing_flag` is true |
| `event_time` | BIGINT | When the thing happened (bar close, period end) |
| `published_at` | BIGINT | When the source made it public |
| `vendor_available_at` | BIGINT | When the vendor could first serve it |
| `ingested_at` | BIGINT | When the platform stored it |
| `first_usable_at` | BIGINT | Earliest time a model may use it. The only time models filter on |
| `timezone` | VARCHAR | IANA zone of the source's local times |
| `currency` | VARCHAR | ISO 4217 |
| `adjustment_method` | VARCHAR | `none`, `split_adjusted`, `split_and_dividend_adjusted` |
| `vintage` | INTEGER | 0 for the first release, +1 for each revision of the same event |
| `missing_flag` | BOOLEAN | True when the source reported no value |
| `license` | VARCHAR | Licence or terms the row was obtained under |
| `collection_mode` | VARCHAR | `live` or `backfill` |

Rules enforced in code:
- `first_usable_at` ≥ max(`event_time`, `published_at`, `vendor_available_at`). In `live` mode it is also ≥ `ingested_at`.
- For backfills the collector adds a per-source lag (`backfill_lag_seconds` in the fixture, config later).
- `missing_flag` is true exactly when `value` is null.
- Rows are never updated. A revision is a new row with a higher `vintage`.
- An as-of read returns rows with `first_usable_at` strictly before the decision time, and the highest usable vintage for each (instrument, vendor, field, event_time).

## 2. Forecast (built)

| Field | Type | Meaning |
| --- | --- | --- |
| `forecast_id` | derived | `fc_` hash of every field except `issued_at` |
| `model_id`, `model_version` | str | Registry key of the model |
| `asset_id` | str | `instrument_id` being forecast |
| `issued_at` | datetime | When the forecast was written |
| `as_of` | datetime | Decision time. No input is usable at or after it |
| `target_definition` | str | Plain statement of what is forecast |
| `target_start`, `target_end` | datetime | Window of the outcome |
| `expected_excess_return` | float, optional | Only when `calibration_status` is `calibrated` |
| `signal_strength` | float, optional | Rank or score when not calibrated |
| `quantiles` | map, optional | Only when calibrated |
| `training_cutoff` | datetime | Last data used to fit |
| `data_snapshot_id` | str | `snap_` hash of the input observation IDs |
| `feature_snapshot_id` | str | `feat_` hash of the features |
| `calibration_status` | enum | `calibrated`, `signal_strength_only`, `not_available` |
| `evidence_refs` | list of str | Claim card or experiment IDs |
| `eligible_for_orders` | bool | False blocks any order from this forecast |

Rules enforced: exactly one of `expected_excess_return` and `signal_strength` is set. `training_cutoff` ≤ `as_of` ≤ `issued_at`. `target_start` ≥ `as_of`.

## 3. OrderIntent (built)

| Field | Type | Meaning |
| --- | --- | --- |
| `client_order_id` | derived | `ord_` hash of every field except `rationale`. Stable across retries |
| `forecast_id` | str | Forecast that produced it |
| `asset_id` | str | Instrument |
| `side` | enum | `buy` or `sell` |
| `quantity` | float > 0 | Shares |
| `limit_price` | float, optional | Absent for a marketable order |
| `strategy_id`, `strategy_version` | str | What proposed it |
| `session_date` | str | ISO date of the session it is for |
| `venue` | enum | `SIMULATION` or `PAPER`. There is no live value |
| `rationale` | list of str | At most six short lines |

## 4. Quote and RiskContext (built)

`Quote`: `asset_id`, `bid` > 0, `ask` > 0, `quote_time`.

`RiskContext`: `now` plus the fields below. Each is optional, and a missing one blocks the order.

| Field | Type | Meaning |
| --- | --- | --- |
| `kill_switch_engaged` | bool | State of the kill switch |
| `market_open`, `market_halted` | bool | Session and halt state |
| `broker_connected` | bool | Adapter connection state |
| `account_state_known` | bool | Last reconciliation succeeded |
| `instrument_mapping_certain` | bool | Symbol maps to exactly one instrument |
| `quote` | Quote | Latest quote for the instrument |
| `equity`, `day_start_equity` | float | Account equity now and at the session start |
| `position_value` | float | Current value held in the instrument |
| `cluster_value` | float | Current value held in the instrument's correlated cluster |
| `adv20_shares` | float | 20-day average daily volume in shares |

## 5. RiskDecision, Fill, BrokerAck (built)

`RiskDecision`: `risk_decision_id` (derived), `client_order_id`, `verdict` (`approved` or `blocked`), `reasons` (one line per failed check, prefixed by check name), `checks_run`, `limits_hash`, `decided_at`.

`Fill`: `fill_id` (derived from client_order_id and fill_seq), `client_order_id`, `asset_id`, `side`, `quantity`, `price`, `venue`, `filled_at`, `fill_seq`.

`BrokerAck`: `client_order_id`, `status` (`accepted`, `filled`, `partially_filled`, `rejected`, `unknown`), `venue`, `fills`, `message`.

## 6. Audit record (built)

Table `audit_log` in SQLite. UPDATE and DELETE are refused by triggers.

| Column | Type | Meaning |
| --- | --- | --- |
| `seq` | INTEGER, primary key | 1, 2, 3 with no gaps |
| `event_time_utc` | TEXT | When the event happened |
| `received_time_utc` | TEXT | When the platform recorded it |
| `actor` | TEXT | `system:<service>` or `user:aditi` |
| `strategy_version` | TEXT | `config:<config_version>:<config_hash>` plus model version where relevant |
| `event_type` | TEXT | See list below |
| `entity_id` | TEXT | ID of the object the record is about |
| `payload_json` | TEXT | Canonical JSON of the object |
| `prev_hash` | TEXT | `record_hash` of the previous row, 64 zeros for the first |
| `record_hash` | TEXT, unique | SHA-256 of `prev_hash` plus the canonical JSON of the other columns |

Event types in use: `observation_ingested`, `forecast_issued`, `order_intent_created`, `no_order`, `risk_decision`, `broker_ack`, `fill`. Planned: `approval`, `rejection`, `cancellation`, `kill_switch`, `rule_change`, `signal_status_change`, `reconciliation`, `composite_run`.

## 7. Composite records

### 7.1 Evidence and EdgeEstimate (planned, `composite/edge.py`)

`Evidence`: `kind` (`family_prior`, `paper`, `out_of_sample`), `value` (annual return at 10% volatility, as a fraction), `variance`.

`EdgeEstimate`: `mu_hat`, `variance`, `prob_positive`, `evidence_used`.

### 7.2 Signal state (planned as a registry table, used as an in-memory record now)

| Field | Meaning |
| --- | --- |
| `signal_id`, `signal_version` | Registry key |
| `family` | Family name |
| `signal_type` | `cross_sectional`, `time_series`, `event`, `practitioner` |
| `horizon_days` | h_s |
| `tier` | 0 to 6 |
| `selection_cutoff` | Date after which returns count as out of sample |
| `oos_days`, `oos_events` | Size of the out-of-sample record |
| `oos_mean_annual`, `oos_se_annual`, `oos_var_annual` | r̄_s, σ_s, v_s from spec C.3 |
| `vol_scale` | g_s, the scale that brings the signal to 10% volatility |
| `paper_return_annual`, `paper_se_annual`, `modeled_cost_annual`, `delta_group` | Paper evidence, when it exists |
| `feed_healthy` | Data feed state today |
| `tier4_long_short_pass`, `tier4_long_only_pass` | The two parts of the Tier 4 economic test |

### 7.3 CompositeRun, the C.10 output contract (planned, `composite/run.py`)

| Field | Meaning |
| --- | --- |
| `composite_run_id` | `crun_` hash |
| `as_of` | Decision time |
| `universe_hash` | Hash of the sorted asset IDs |
| `config_hash` | Config in force |
| `signals` | Per signal: `signal_id`, `tier`, `mu_hat`, `prob_positive`, `weight`, `capital_weight`, `eligible`, `reasons` |
| `unallocated_weight` | 1 minus the sum of weights |
| `score` | S per asset |
| `alpha` | α per asset, null when not calibrated |
| `calibration_status` | `calibrated` or `signal_strength_only` |
| `optimizer_status` | `optimal`, `vol_below_target`, `reduce_only`, `not_run`, `failed` |
| `target_weights` | x per asset |
| `ex_ante_vol_annual` | Forecast volatility of the target book |
| `contributions` | Per asset, each signal's share of its α |

## 8. Planned schemas, from the spec

**Claim card:** `claim_id`, `source_id`, `source_type`, `canonical_url`, `doi`, `title`, `author_ids`, `published_at`, `revised_at`, `ingested_at`, `first_actionable_at`, `market`, `instruments`, `target`, `horizon`, `direction`, `probability_if_stated`, `definition`, `mechanism`, `data_required`, `code_available`, `peer_review_status`, `replication_links`, `conflicts`, `license`, `test_plan_id`, `evidence_status`, `capture_hash`.

**Source profile:** `source_id`, `identity_status` (`verified`, `unresolved`, `disputed`), `domain_evidence`, `claim_testability`, `track_record`, `conflicts`, `latency`, `evidence_label`.

**Experiment manifest:** `experiment_id`, `question`, `null_hypothesis`, `study_type`, `universe`, `period`, `outcome`, `lookback`, `holding_period`, `scheme` (train, validation, test, embargo), `variants_tried`, `independence`, `costs`, `benchmarks`, `decision_rule`, `registered_at`, `result`, `status`.

**Instrument:** `instrument_id`, `symbol_history` (symbol, exchange, valid_from, valid_to), `security_type`, `type_inferred`, `sic_code`, `industry_ff12`, `listed_at`, `delisted_at`, `tag` (`direct`, `proxy`, `research_only`).

Statuses for claims and signals: `DISCOVERED`, `EXTRACTED`, `NEEDS_DATA`, `REPRODUCING`, `REPRODUCED`, `FAILED`, `REPLICATED`, `OOS_PASSED`, `SHADOW`, `ELIGIBLE_FOR_REVIEW`, `PAPER`, `SUSPENDED`, `RETIRED`.

Data labels: `SURVIVORSHIP-BIASED`, `NOT AVAILABLE`, `type_inferred`, `backfill`.
