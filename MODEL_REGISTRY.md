# MODEL_REGISTRY.md

Source: `SPEC.md` v3.2, sections "The Composite", "Model laboratory" and "Evidence tiers". This file defines what a registry entry holds, lists every model and signal the platform knows about, and gives each one's honest status.

Two signals hold Tier 3 on academic evidence (momentum and short-term reversal). None holds Tier 4, because no executable approximation has been tested on real platform data. Published factors can be taken to Tier 4 on free portfolio returns once the Phase 3 research engine exists (`QUESTIONS.md` Q1 and Q14).

## 1. Registry entry schema

Every model or signal registers these fields before it can issue a forecast.

| Field | Meaning |
| --- | --- |
| `model_id` | Stable name, lower snake case |
| `model_version` | Semantic version. Any change to code or parameters bumps it |
| `level` | A (transparent baseline), B (structured statistical), C (supervised ML), D (experimental) |
| `scope` | Market, instruments and universe it applies to |
| `signal_type` | `cross_sectional`, `time_series`, `event`, `practitioner`, or `aggregate` for the Composite |
| `family` | One of the 13 JKP themes, or trend, reversal, earnings events, corporate actions, macro, volatility, stat arb, news, biotech events, or a practitioner domain |
| `horizon_days` | h_s in trading days |
| `data_contract` | Observation fields it reads, with the vendor |
| `output_type` | `signal_strength`, `expected_excess_return`, `probability`, `volatility` |
| `refit_schedule` | When parameters are re-estimated |
| `benchmark` | What it must beat out of sample |
| `selection_cutoff` | Latest of the paper's sample end, first public date and the platform's last design choice |
| `evidence_tier` | 0 to 6 |
| `status` | One of the claim and signal statuses in `DATA_DICTIONARY.md` |
| `oos_record` | Out-of-sample days or events, r̄_s, σ_s, or NOT AVAILABLE |
| `trial_count` | Number of variants tried, from the experiment registry |
| `evidence_refs` | Claim cards and experiments |
| `code_path` | Module that implements it |
| `data_labels` | For example SURVIVORSHIP-BIASED |
| `approved_by`, `approved_at` | Set when Aditi approves a promotion above Tier 4 |
| `promotion_policy` | The strategy's own shadow trade count and precision requirement, or the defaults |
| `monitoring_policy` | The strategy's own deterioration window and alert level, or the defaults |
| `data_licenses` | License IDs of the data it uses. Any license that does not permit paper trading keeps it research only |
| `parameters_varied` | Config paths its experiments varied. Only provisional and empirical paths are allowed |

Rules:
- A forecast carries `model_id` and `model_version`, and the audit log stores both. Rollback to a prior version is one config change.
- A model in Level B, C or D earns a place only by beating the level below it out of sample.
- An LLM never sets a number used in trading. No registry entry may list an LLM as the source of a forecast value.
- Promotion above Tier 4 needs Aditi's approval. Demotion is automatic and logged.

## 2. Evidence tiers

| Tier | Name | Gate to reach it | Unlocks |
| --- | --- | --- | --- |
| 0 | Observation | Raw data | Feeds everything |
| 1 | Claim | An idea with no reproduction | Hypothesis Factory queue |
| 2 | Reproduced | Same sign, and effect inside the paper's interval or at least half its size, on the original definitions and period | Independent testing |
| 3 | Independently replicated | Same sign and significant at 5% on new data, independence recorded. A platform discovery needs t above 3.0 and FDR under 5% (Benjamini-Yekutieli) and a pass on an untouched holdout | Out-of-sample economic test |
| 4 | Executable approximation passes | The tradable stock-level version, evaluated by the platform on platform data with realistic costs: lower bound of the block-bootstrap 90% interval of net excess return above zero at doubled costs (provisional level). Cross-sectional signals pass twice: long-short, and long-only. Academic evidence enters the edge estimate but cannot pass this tier alone | Composite at shadow weight, prospective shadow trading starts |
| 5 | Prospectively validated | `promotion_check`: at least 63 prospective trading days, the strategy's trade count and precision, realized return inside the band, tracking within the limit. Retrospective records never count | Paper capital in the Composite |
| 6 | Paper-deployed | Trading in the paper account under governance | Eligible for a future live review |

A result on data without delisted securities is labeled SURVIVORSHIP-BIASED and cannot pass any gate.

## 3. Registered models

### 3.1 `fixture_baseline` 0.1.0

| Field | Value |
| --- | --- |
| Level | none. Test harness, not a trading model |
| Scope | The synthetic instrument `inst_TEST` in `tests/fixtures/phase0_event.json` |
| Signal type | time_series |
| Horizon | 5 calendar days (fixture value) |
| Data contract | `close` from vendor `fixture` |
| Output | `signal_strength` in {−1, 0, +1}: sign of last close minus first close in the window |
| Benchmark | none |
| Evidence tier | none |
| Status | Built. Exists to push one event through every contract in Phase 0 |
| Routing | Internal simulator only. `build_intent` refuses a PAPER venue for this model |
| Code | `candleisgreen/models/fixture_baseline.py` |

### 3.2 `composite` 0.1.0

| Field | Value |
| --- | --- |
| Level | Aggregate over eligible signals |
| Scope | US stocks and ETFs in universe U_t |
| Signal type | aggregate |
| Horizon | 21 trading days for α |
| Data contract | Signal z-scores, signal return series, residual volatility, factor model, quotes and ADV |
| Output | `expected_excess_return` when calibrated, else `signal_strength` |
| Refit schedule | Weights on the first trading day of each month, and at once on a demotion or feed failure. Calibration monthly |
| Benchmark | Frozen-weight Composite, champion against challenger, and a broad US equity ETF mixed with cash to the same volatility target |
| Evidence tier | Not applicable. It inherits the tiers of its signals |
| Status | Built and tested on synthetic inputs, C.2 to C.10 plus the C.12 tests. It has no real eligible signals, so it produces no orders |
| Code | `candleisgreen/composite/` |

Composite parameters, all in `config/default.yaml` under `composite`:

| Step | Parameter | Default |
| --- | --- | --- |
| C.2 | Winsor percentiles | 1 and 99 |
| C.2 | Time-series window and clip | 252 days, ±3 |
| C.2 | EMA half-life | 0.5 × h_s |
| C.3 | Research volatility target, research NAV | 10%, $1M |
| C.3 | Newey-West lag | min(h_s, 63, T/4) |
| C.4 | δ: US published, non-US published, other published | 0.42, 0.74, 0.74 |
| C.4 | ω factor | 0.5 |
| C.4 | Cold-start τ, τ floor | 5%, 1% |
| C.4 | Signals needed for a family prior, for replacing δ | 5, 20 |
| C.5 | Minimum tier, capital tier | 4, 5 |
| C.5 | Minimum P_s, out-of-sample days, events | 0.80, 252, 30 |
| C.6 | Covariance window, minimum | 756, 252 days |
| C.6 | Signal cap, family cap | 20%, 35% |
| C.6 | Monthly change limit | larger of 25% relative and 2 points. New signals enter at 5% or less |
| C.7 | IC horizon, shrink days, α clip | 21 days, 252, 3 |
| C.7 | Calibration slope band, minimum t | 0.5 to 1.5, 2 |
| C.8 | Factors, window | 15, 252 days |
| C.8 | κ and its floor | 0.5, 0.5 |
| C.8 | Volatility target (upper bound), sector cap, no-trade band | 12%, 25%, 0.25% |

## 4. Planned models, in build order

None of these exists in code. Each enters at Tier 1 and moves only through the gates above.

| Phase | `model_id` | Level | Family | Type | Horizon | Benchmark |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `ts_momentum_252_21` (built, Tier 1, simulator only) | A | trend | time_series | 21 | Buy and hold, volatility matched |
| 3 | `xs_momentum_12_1` (built, Tier 3 on academic evidence) | A | momentum (JKP) | cross_sectional | 21 | Universe return |
| 3 | `st_reversal_5` (built, Tier 3 on academic evidence) | A | short-term reversal (JKP) | cross_sectional | 5 | Universe return |
| 3 | `buy_and_hold` | A | none | benchmark | none | Cash |
| 3 | Two published factor reproductions, one expected to pass and one expected to fail | A | to be chosen from the claim cards | cross_sectional | per paper | Per paper |
| 5 | Regularized linear, GARCH and HAR volatility, shrinkage covariance, event-study regressions | B | several | several | several | The Level A model in the same family |
| 5 | Elastic net, calibrated logistic regression, gradient-boosted trees | C | several | several | several | The Level B model in the same family |
| later | Sequence models, embeddings, reinforcement learning, meta-labeling | D | research only | | | Level C, net of costs |

## 5. Signal families

| Family | Examples | Horizon | Main failure modes |
| --- | --- | --- | --- |
| Trend and momentum | Volatility-scaled trend, return ranks, breakouts | Weeks to months | Whipsaw, crowding, costs |
| Reversal | 1 to 5 day reversal with liquidity filters | Days | Bid-ask bounce, illiquidity |
| Fundamental factors | Value, quality, profitability, investment, low risk, accruals, issuance | Months | Accounting lookahead, delistings, capacity |
| Earnings events | Standardized unexpected earnings, drift, revisions | Days to months | Stale estimates, event timing |
| Corporate actions | Insider clusters, buybacks, spinoffs, index changes | Days to months | Announcement against filing date |
| Macro and cross-asset | Rate and inflation surprises, curve, credit spreads | Days to quarters | Data revisions, unstable correlations |
| Volatility | EWMA, GARCH, HAR, implied minus realized | Days to weeks | Stale or sparse option data |
| Statistical arbitrage | Cointegrated pairs and baskets | Days to weeks | Breakdown of the relationship, borrow |
| News and text | Entity-event extraction, surprise, novelty | Minutes to days | Duplicates, delayed feeds |
| Biotech catalysts | FDA action dates, trial phase, endpoints, cash runway | Event-dependent | Binary gaps, misread trial science |
| Practitioner claims | Scored claims from sources with 30 or more claims in a domain | Days to months | Selection bias, vague targets |
| Options and flow | Greeks, surface, dealer exposure scenarios | Minutes to weeks | Dealer positioning is inferred |

The 13 JKP themes used as equity families: accruals, debt issuance, investment, leverage, low risk, momentum, profit growth, profitability, quality, seasonality, size, short-term reversal, value.

## 6. Where LLMs are used

| Task | Model tier |
| --- | --- |
| Claim cards, research digest, reasoning summaries | Larger model, budget-capped, cached |
| News tagging, entity linking, translation, glossary lookups | Small model or rules |
| Anything that sets a number used in trading | Never an LLM |

The platform runs without a paid LLM. No LLM call exists in the code today.
