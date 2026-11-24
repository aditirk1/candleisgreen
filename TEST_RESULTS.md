# TEST_RESULTS.md

Latest full run: 2026-11-24, **306 passed, 0 failed** in about 122 seconds on Python 3.13.

Only results that actually ran are listed. Command: `make ci` (which runs `.venv/bin/python -m pytest`).

## Phase 0, 2026-11-17, Python 3.13.18

Result: **69 passed, 0 failed** in about 2 seconds.

### Acceptance test 1: one offline event flows end to end with immutable IDs. PASSED

`tests/test_phase0_end_to_end.py`

| Test | What it shows |
| --- | --- |
| `test_event_flows_end_to_end` | Fixture bars, store, as-of read, forecast, order intent, risk approval, simulator fill. 11 audit records in order, each step pointing at the one before it, chain intact |
| `test_ids_are_identical_across_independent_runs` | Two runs in separate directories give identical IDs and the same audit head hash |
| `test_forecast_used_only_data_known_at_decision_time` | The Nov 16 close is in the store and is not used for the Nov 13 decision |
| `test_stale_quote_blocks_and_nothing_fills` | A 30 second old quote gives a blocked decision, no broker call and no fill |
| `test_kill_switch_blocks` | Kill switch on gives no fill |
| `test_falling_prices_give_no_order` | Long-only: a negative signal creates no order |
| `test_fixture_model_cannot_be_routed_to_a_paper_broker` | The stub model is simulator-only |

Command to see it: `make phase0`. Output on this run: verdict approved, 48 shares of `inst_TEST` filled in SIMULATION, audit chain intact.

### Acceptance test 2: a planted lookahead leak is caught. PASSED

`tests/test_pit_and_lookahead.py`

| Test | What it shows |
| --- | --- |
| `test_planted_lookahead_leak_is_caught` | A model fed rows read around the as-of view raises `LookaheadError` |
| `test_revised_value_is_invisible_before_its_revision` | Failure fixture "lookahead from a revised filing": the original value is seen before the revision date and the revised one after |
| `test_as_of_view_hides_values_not_yet_usable`, `test_boundary_is_strict` | A value usable exactly at decision time is not visible |
| `test_guard_passes_clean_inputs_and_names_the_offender` | The error names the offending observation |
| `test_duplicates_are_ignored_and_rows_are_append_only`, `test_parquet_export_round_trips` | Store behavior |

### Contracts, audit, risk and broker. PASSED

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_contracts.py` | 16 | Naive datetimes rejected, daylight-saving boundary (failure fixture), ID stability, immutability, forecast rules, config unknown keys rejected, live trading cannot be enabled, hard limits equal the spec defaults |
| `tests/test_audit.py` | 5 | Chain links, UPDATE and DELETE refused, edits and removals behind the triggers detected |
| `tests/test_risk_and_broker.py` | 44 | 20 blocking cases including stale quote (failure fixture), halted market (failure fixture) and each hard limit, the 15 second boundary, a raising check, a property test that any missing input blocks, unapproved and duplicate submissions, attempted live order (failure fixture), non-paper endpoints refused |

### Required failure fixtures from the spec

| Fixture | Status |
| --- | --- |
| Lookahead from a revised filing | Tested |
| Stale quote | Tested |
| Halted market | Tested |
| Daylight-saving boundary | Tested |
| Attempted live order | Tested |
| Duplicate submission (Phase 2 acceptance, covered early on the simulator) | Tested |
| Split or dividend error, ticker change, survivorship-biased universe, multiple testing without correction, duplicate news story, partial fill, broker timeout, stop gapped through, missing FX rate, calibration collapse, missing consensus estimate, new paper contradicting an active signal | Not built yet. Each belongs to a later phase |

### Not tested

- The risk service as a separate process. It is in-process in Phase 0.
- Any broker paper account. No network call exists in the code.
- Python 3.12 and 3.14. Only 3.13 was available here.

## Composite (spec section C), 2026-11-17, Python 3.13.18

Result: **42 passed** (`tests/test_composite_steps.py` 24, `tests/test_composite_c12.py` 18). All inputs are synthetic.

### C.12 required tests

| Requirement | Test | Status |
| --- | --- | --- |
| Synthetic signals with known edges are recovered within their stated intervals at the stated rate | `test_intervals_cover_true_edges_at_the_stated_rate`: 90% intervals cover the true edge in 88% to 92% of 4000 draws | Passed |
| Pure-noise signals are excluded in at least 95% of runs | `test_pure_noise_is_excluded_by_the_joint_gate`: 600 zero-edge signals through Tier 3, Tier 4 and P_s | Passed |
| Same, Tier 4 alone | `test_tier4_alone_admits_noise_at_its_nominal_rate`: about 5% admitted, which gives no margin (REVIEW E30) | Passed, property pinned |
| Two identical copies get the same total weight as one | `test_identical_copies_share_one_budget`, within 2 points before caps | Passed |
| An input usable after decision time fails the build | `test_input_usable_after_decision_time_fails` raises `LookaheadError` | Passed |
| A failed calibration blocks new positions | `test_failed_calibration_blocks_new_positions`: reduce-only, no new names, no increases | Passed |
| The optimizer never breaks a hard limit | `test_optimizer_respects_every_hard_limit`, 6 random books with concentrated alpha and a binding order-size limit | Passed |
| The risk check rejects a deliberately injected book | `test_risk_check_rejects_an_injected_book` | Passed |
| Frozen-weight and champion-challenger benchmarks run every day | `test_benchmarks_run_beside_the_live_composite` | Passed |
| Three signals leave 40% unallocated (added in v3.1) | `test_caps_with_three_signals_leave_forty_percent_unallocated` | Passed |

### Step tests

| Step | What is checked |
| --- | --- |
| C.11 worked example | Edge 3.04%, standard deviation 1.44%, probability 0.98. Noise example 0.40% and 0.57 |
| C.4 | δ cancels for paper-only evidence (REVIEW E3), cold-start prior and τ floor, δ replacement needs 20 signals |
| C.5 | Tier, P_s, history length, events, feed health, SURVIVORSHIP-BIASED label |
| C.2 | Winsorized z-scores, sector-neutral z-scores, time-series scores use only the past, EMA half-life, event signals stay inside their window, practitioner decay |
| C.6 | Caps and redistribution, change limit with floor, entry cap and immediate removal, non-negative within-family weights, HRP ordering |
| C.7 | Score scaling, volatility scale g_s, α shrinkage and clip, calibration on the unshrunk forecast (REVIEW E12), Newey-West IC t-statistic under overlap (REVIEW E13) |
| C.8 | Volatility target treated as an upper bound |
| C.10 | Output record fields, Tier 4 is shadow only, the run ID is reproducible |

### Not tested

- Any real data. No signal has a real out-of-sample record.
- Optimizer speed at full universe size (about 3,000 names). The tested books have 40 to 60 names and solve in under a second.

## Research portfolios and cost model (spec C.3), 2026-11-17

Result: **8 passed** (`tests/test_research_portfolio.py`). All inputs are synthetic.

| Test | What it shows |
| --- | --- |
| `test_weights_use_no_future_returns` | Changing returns after day 150 leaves every weight up to day 150 unchanged |
| `test_cross_sectional_is_dollar_neutral_and_hits_the_vol_target` | Weights sum to zero and realized volatility is within 1.5 points of 10% |
| `test_planted_edge_is_recovered` | A planted edge is recovered within 3 standard errors, and pure noise comes back near zero |
| `test_costs_are_charged_and_grow_with_the_spread` | Net equals gross minus cost, and a 10x wider spread costs more than 5x as much |
| `test_borrow_is_charged_only_on_short_legs` | With no spread or impact, cost equals borrow on the short leg plus SEC fees on sells, to the cent |
| `test_long_only_series_and_vol_scale` | The top third beats the universe before costs. With daily full turnover, costs exceed that edge |
| `test_no_weights_before_enough_history` | No position until 21 days of history exist |
| `test_builder_output_feeds_the_daily_composite_run` | Builder output for two real signals and one noise signal goes through the economic test into `run.daily`. Both real signals are eligible and get capital weight. Noise does not |

## Capability map, 2026-11-17

Result: **9 passed** (`tests/test_capabilities.py`). Every limited or unavailable capability states its reason. Options data, real-time consolidated quotes, intraday trading, analyst estimates, licensed news and non-US execution each raise `CapabilityNotAvailableError` when code asks for them. A capability entry without a reason is rejected at load time.

## Spec v3.2 decisions, 2026-11-22

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_parameters.py` | 6 | Every config value is classified, hard limits are safeguards, research thresholds are provisional, empirical values cite sources, experiments cannot vary safeguards or external facts, each basis requires its own record |
| `tests/test_decisions_v32.py` | 17 | Q9 retrospective and prospective records, Q3 license refusal for JKP-derived orders, Q4 execution window and delayed-quote blocks end to end, Q10 unknown sectors pooled and capped in the optimizer and the book check, Q12 module boundaries |
| `tests/test_monitoring_promotion.py` | 9 | Q6 infrastructure pause and deterioration test with sample uncertainty, Q8 promotion requirements and per-strategy policy, Q14 academic evidence with an implementation gap and no capital without a prospective tier |
| `tests/test_risk_and_broker.py` | 44 | Adds the execution window, quote feed, zero quote size, limit distance from mid, pending orders, resting non-marketable limits and slippage against arrival mid |

Not tested yet, because the code belongs to later phases: the forward recorder and its completeness flags (Phase 1), the execution window comparison and SIC classifications (Phase 2), the clustering stability test and the experiment registry's development history (Phase 3), and the Oracle fallback and heartbeat (Phase 1). Python 3.12 has not been run.

## Phase 1, US paper vertical slice, 2026-11-24

Acceptance test: **passed**. Approval, rejection, fill, stale-feed block and kill switch are verified end to end, with the risk engine running in its own process.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase1_acceptance.py` | 11 | Decision proposes buys for uptrends only, approval then fill, rejection means no order, auto simulation stays inside the limits, stale quote blocks, delayed consolidated quote blocks, kill switch blocks and only Aditi can release it, risk service down blocks everything, outside the window blocks, a Tier 1 model cannot reach a paper account, rerunning execution does not repeat orders |
| `tests/test_recorder.py` | 10 | Delisted name kept with its history, ticker change keeps one instrument ID, split and dividend stored with raw bars, backfill flagged without a snapshot, live session recorded once, live values usable only after collection, closed day recorded, free-plan delay respected, security type inferred, live transport needs paper keys |
| `tests/test_ts_momentum.py` | 5 | Split and dividend adjustment only once effective, score sign and clip, skipped month ignored, universe excludes the delisted name, a split does not look like a crash |
| `tests/test_jobs.py` | 5 | Record twice stores the same result, catch-up fills missed weekdays, fallback runs only on a stale heartbeat, missing heartbeat counts as stale, no session before the free data is ready |
| `tests/test_api.py` | 2 | Approve, reject, execute and kill switch through the API, and an unreachable risk service reported |

### Interface check

`make screens` drives the real interface with Playwright against the demo. Last run, 2026-11-24 00:40 ET, all 11 checks passed: SIMULATION label visible, positions table and equity curve drawn, approval queue present, approve and reject both work, kill switch shown as ON after engaging, no em dashes, semicolons or middle dots in visible text, modes in plain words, no page errors. Screenshots are in `docs/screens/`.

### Not tested in Phase 1

- Any live Alpaca call. No paper keys exist in the build environment, so the client ran only against the offline synthetic market (DECISIONS D-033).
- The Oracle Cloud schedule itself. The heartbeat and fallback logic are tested locally.

## Phase 2, broker paper and filings, 2026-11-24

Acceptance test: **passed**. A duplicate submission is not repeated, every financial figure traces to an SEC filing, and there is no beat or miss without a consensus estimate.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase2_broker.py` | 10 | Limit order with the client ID fills, duplicate submission not repeated, lost response queried not resubmitted, failure before acceptance retried once, two uncertain failures leave the state unknown, resting and partial fills, paper adapter refuses simulation and unapproved orders, reconciliation, paper execution through the executor fills and reconciles without repeats, a reconciliation mismatch blocks every order |
| `tests/test_phase2_filings.py` | 17 | Every SEC figure has an accession number and filing URL, figures usable only from the acceptance time, a restatement becomes a new vintage, the 17:30 ET fallback, scorecard has no beat or miss and labels consensus NOT AVAILABLE, scorecard shows only what was filed by then, SIC to Fama-French 12 with version and date, eight SIC mapping cases, live SEC transport needs a User-Agent, slippage by window |

SEC fixtures are trimmed real EDGAR responses for Apple, fetched 2026-11-24 (`tests/fixtures/sec/`).

Interface check, 2026-11-24 00:51 ET: all 14 Playwright checks passed, now including the Earnings screen (industry shown, every row links to its filing, no beat or miss).

Not tested: a live Alpaca paper account (no keys) and a live SEC pull with a real User-Agent.

## Phase 3, research engine and the first Composite, 2026-11-24

Acceptance test: **passed**. The full evidence chain is shown in the interface, a negative result is stored and visible, and the Composite output traces to each signal's weight and evidence.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase3.py` | 6 | Momentum (Jegadeesh and Titman 1993) reproduces at 1.28% a month against the paper's 1.31% and replicates after 1993 (t 1.97). Betting against beta fails reproduction and stays in the failure archive with its selection note. Academic evidence stops at Tier 3. The evidence chain links claim, experiments and results. Registry rules: no conclusion without a recorded variant, no varying a safeguard, no plan change after registration, no variants after completion. Composite v0 traces every signal's weight to its evidence, labels synthetic and retrospective results, and allocates nothing |
| `tests/test_research_portfolio.py` | 9 | Adds the gross leverage cap |

Academic data: trimmed real Open Source Asset Pricing files, release 2026.10, CC BY 4.0 (`tests/fixtures/osap/`).

Interface check, 2026-11-24 01:12 ET: all 21 Playwright checks passed, now including the Composite screen (every signal listed, RETROSPECTIVE and SYNTHETIC labels, PROVISIONAL and SAFEGUARD tags on exclusion reasons) and the Research screen (evidence chain opened from the Composite screen, failure archive, negative result visible).

## Phase 4, news and teaching, 2026-11-24

Acceptance test: **passed**. A replay cannot see later news or prices at earlier timestamps (`test_replay_cannot_see_later_prices_news_or_corrections`). A September close corrected in late October shows its original value until the replay clock passes the correction time, then the corrected vintage.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase4.py` | 7 | Real SEC and Federal Reserve feeds parse with hashes and short summaries, never usable before first seen, ingesting twice adds nothing, duplicate stories cluster, hostile XML is refused, tickers linked from exchange mentions, the replay acceptance test, predict-first with Brier score and a calibration table that never counts an unrevealed outcome |
| `tests/test_api.py` | 3 | Adds replay refusing a future clock, a replay prediction hidden until the clock passes its horizon, and Why not for a down-trending ticker |

RSS fixtures are real feeds fetched 2026-11-24 (`tests/fixtures/rss/`).

Interface check, 2026-11-24 01:13 ET: all 29 Playwright checks passed, now including News (clustered official stories), Reasoning (model and version, agreeing and opposing signals, Why not), and Learn (no later price at the replay clock, outcome hidden until the horizon passes, calibration not counting it, outcome revealed after advancing).

## Phase 5, Hypothesis Factory and model levels B and C, 2026-11-24

Acceptance test: **passed**. A model update never changes risk limits or permissions (`test_model_updates_never_change_risk_limits_or_permissions` fingerprints every config and registry file and the risk service's limits before and after a full research day). A contradicting paper opens a re-evaluation case (`test_contradicting_paper_opens_a_reevaluation_case`).

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase5.py` | 9 | Both acceptance tests, factory duplicates, NEEDS_DATA with a free substitute and near-duplicate links, a built-in study recording a negative result, promotion above Tier 4 only through Aditi, drift alert demotes and opens a case, practitioner scoring with Wilson intervals, purged walk-forward, Levels B and C compared with Clark-West and Diebold-Mariano and never switching on synthetic data |
| `tests/test_phase5_criteria.py` | 6 | Benjamini-Yekutieli, FDR on noise, the new-factor rule, Clark-West when nested, subperiod stability, clustered event studies |

## Phase 6, global research, 2026-11-24

Acceptance test: **passed**. Every non-US instrument is research only and cannot receive orders, and a week of follow-the-sun jobs (7 days, 4 slots) runs with no manual step and changes nothing when rerun.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_phase6.py` | 12 | FX split adds up, real FRED rates with yen inversion, missing FX rate never filled (spec failure fixture), only direct and proxy instruments receive orders, taxonomy tags, NYSE calendar from the rule table, every non-US exchange research only, JKP momentum evidence by market tagged noncommercial and refused for trading, the follow-the-sun week |

Interface check, 2026-11-24 01:26 ET: all 39 Playwright checks passed across nine screens, now including the research digest, re-evaluation cases, model comparisons, Aditi-only promotion decisions, and the Global screen.

## Safety extras and the remaining screens, 2026-11-24

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_safety_extras.py` | 6 | Tightening a hard limit applies at once, loosening waits 24 hours and needs Aditi's confirmation, only Aditi can act and values are checked, the risk service enforces changed limits, the pre-open check cancels risky buys and never adds, a shared store survives 2,000 concurrent reads |
| `tests/test_api.py` | 4 | Adds Opportunities, Markets (no price after the clock), Backtests, Experts, Audit and Rules with the limit workflow through the risk service and its refusal reason, and Settings (credential status only, monthly cost 0) |

Interface check, 2026-11-24 01:44 ET: all 59 Playwright checks passed across fifteen screens on fresh demo data, with no server errors. New checks cover the first-run tour, Opportunities with its evidence pane, Markets with a chart and watchlist, Backtests with trial counts beside every Sharpe, Experts, hard-limit changes on Audit and Rules, Settings, the command bar (`UPCO NEWS`, `RULES`, a plain "why didn't we buy" phrase) and Guide mode (plain labels, Explain this screen, venue label and kill switch still shown).

A first run found a real bug: two simultaneous requests shared one SQLite connection without a lock and one returned an error. Shared connections now go through `candleisgreen/core/sqlite_shared.py`, which runs and fetches each statement under a lock.

## Pre-open job and correlation clusters, 2026-11-24

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_safety_extras.py` | 8 | Adds the scheduled pre-open check cancelling a halted buy, cancelling every buy when asset status cannot be read, and its slot following New York daylight saving |
| `tests/test_clusters.py` | 6 | Planted groups recovered, market-only correlation not merged into one cluster, stability score, monthly runs stored and reused, sector fallback when unstable, a name outside a stable clustering blocked at execution while a covered name fills |
| `tests/test_phase6.py` | updated | The follow-the-sun week now has six jobs a day, including the pre-open check and a clustering computed once and reused |

## Research Capture Inbox, 2026-11-24

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_inbox.py` | 7 | Hash, time, short summary and claims kept, duplicates detected, full text never stored, links ask for input instead of fetching, HTML read and PDF asks for input, commentary not turned into claims, the nightly review takes claims once, the API |

Interface check: 61 Playwright checks passed, now including an inbox capture from pasted text and a link that asks for input.

## Macro vintages, 2026-11-24

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_macro.py` | 5 | Every vintage stored once, reads as known then (first release, then revision, nothing before release, 17:00 New York cutoff), non-numeric values missing and never filled, paging, NOT AVAILABLE without a key, the Global view |

The fixture is constructed in the documented shape with invented values. Interface check: 62 Playwright checks passed.

## Clinical trials, 2026-11-24

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_trials.py` | 5 | Name normalization, only exact lead-sponsor matches linked with paging followed, unchanged content not stored twice, non-biotech names not queried, changes become events, reads as known then, a revert recorded, trial data refused for paper trading |

The follow-the-sun week now runs eight jobs a day. Interface check: 62 Playwright checks passed.
