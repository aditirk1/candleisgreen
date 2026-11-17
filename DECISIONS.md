# DECISIONS.md

Choices made where the spec was silent, or where the review changed it. Newest last.

| ID | Date | Decision | Reason |
| --- | --- | --- | --- |
| D-001 | 2026-11-17 | The spec's directories (`sources`, `data`, `research`, `models`, `composite`, `backtests`, `risk`, `broker`) live inside one Python package, `candleisgreen/`. `ui/`, `tests/` and `config/` sit at the top | Top-level packages named `data` or `tests` collide with other libraries |
| D-002 | 2026-11-17 | IDs are content hashes: a prefix plus the first 24 hex characters of SHA-256 over canonical JSON | Same content always gives the same ID, so a rerun or a retry cannot create a second object |
| D-003 | 2026-11-17 | Stores hold timestamps as int64 microseconds since the epoch in UTC | Removes timezone and driver ambiguity in DuckDB and SQLite |
| D-004 | 2026-11-17 | `first_usable_at` is strictly before the decision time for a value to be visible | The spec says "before 16:30 ET". A value stamped exactly 16:30 is treated as not yet known |
| D-005 | 2026-11-17 | The Phase 0 point-in-time store is a DuckDB table with Parquet export | Keeps the spec's analytical stack with one small file. Partitioned Parquet comes when volume needs it |
| D-006 | 2026-11-17 | The audit log is one SQLite table with triggers that refuse UPDATE and DELETE, written inside `BEGIN IMMEDIATE` | Append-only at the SQL level, and two processes cannot fork the chain |
| D-007 | 2026-11-17 | In Phase 0 the risk engine runs in-process as a pure function over plain data messages | The process boundary is Phase 1 work. The message types will not change when it moves |
| D-008 | 2026-11-17 | The risk engine runs every check and reports every failure | The Reasoning and "Why not?" screens need the full list |
| D-009 | 2026-11-17 | The daily loss stop blocks buys and leaves risk-reducing sells allowed | The spec says the stop "halts new orders". Blocking sells would trap positions. Flagged for Aditi in the handoff |
| D-010 | 2026-11-17 | `fixture_baseline` is a test harness with no tier. It may only be routed to the simulator | Phase 0 needs one event to flow end to end, and no real model exists yet |
| D-011 | 2026-11-17 | Orders are sliced in the regular session. The opening auction is not used | REVIEW.md E24. An auction order conflicts with two safety invariants |
| D-012 | 2026-11-17 | Python floor is 3.12, target 3.14. Development ran on 3.13 | REVIEW.md O9 |
| D-013 | 2026-11-17 | Review items that need Aditi use the recommended default from `QUESTIONS.md` | Her instruction for the overnight run |
| D-014 | 2026-11-17 | Research portfolios (C.3) are scaled to 10% with an ex-ante estimate from the trailing 63-day returns of today's weights, not from the full factor model | The spec names the Composite's risk model. Fitting it per signal per day is costly. The trailing estimate is also point-in-time and needs no extra data. Revisit if research volatility drifts from target |
| D-015 | 2026-11-17 | Borrow cost for research short legs is 0.5% a year | Judgment call for easy-to-borrow names. Hard-to-borrow names cost far more, which this understates. In config |
| D-016 | 2026-11-17 | Research turnover is the change in target weights and ignores drift from price moves | Simpler and slightly understates turnover |
| D-017 | 2026-11-17 | The Tier 3 replication gate for published signals is a Newey-West t-test, two-sided at 5%, same sign | The spec says "significant at 5% on the new data". The level is in config |
| D-018 | 2026-11-17 | No subscription-based platform and no monthly fee, ever. Only free data, free tools and free accounts | Aditi's rule. Recorded as spec principle 11. Paid options are removed from every document rather than kept as alternatives |
