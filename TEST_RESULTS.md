# TEST_RESULTS.md

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
