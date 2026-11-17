# TEST_RESULTS.md

Latest full run: 2026-11-17 09:40 ET, **119 passed, 0 failed** in about 12 seconds on Python 3.13.18.

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
| `tests/test_risk_and_broker.py` | 34 | 20 blocking cases including stale quote (failure fixture), halted market (failure fixture) and each hard limit, the 15 second boundary, a raising check, a property test that any missing input blocks, unapproved and duplicate submissions, attempted live order (failure fixture), non-paper endpoints refused |

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
