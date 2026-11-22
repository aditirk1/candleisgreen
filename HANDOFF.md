# HANDOFF.md

Last updated: 2026-11-22 01:18 ET. Branch: `spec-review-and-phase0`. Draft pull request: https://github.com/aditirk1/candleisgreen/pull/1

## Timeline note

The overnight run stopped at about 01:35 ET when the usage limit was reached, so no checkpoint was written at 02:40 ET. Everything up to Phase 0 had been committed and pushed by then. Work resumed at 09:21 ET and the Composite was finished and committed after that.

## Done

1. **Review pass.** `REVIEW.md`: errors (E1 to E30), outdated facts, disagreements, open questions, each with a verification status.
2. **Spec v3.1.** `SPEC.md` has every technical fix from the review applied, with a change log at the end. Hard risk limits were not changed. Decisions that need Aditi are in `QUESTIONS.md`, each with the default now in use.
3. **Documents.** `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RISK_POLICY.md`, `MODEL_REGISTRY.md`, `DECISIONS.md`, `TEST_RESULTS.md`, `README.md`.
4. **Phase 0.** Both acceptance tests pass: one offline event flows end to end with immutable IDs, and a planted lookahead leak is caught.
5. **Composite module.** `candleisgreen/composite/` covers all of spec section C: research portfolios and the cost model (C.3), standardization (C.2), edge estimation (C.4), eligibility with the Tier 3 and Tier 4 gates (C.5), weights (C.6), score, α and calibration (C.7), factor model and optimizer (C.8), and the daily run record (C.10). `risk.engine.evaluate_portfolio` gives the independent book check. Every C.12 test passes on synthetic inputs.

6. **Spec v3.2.** Aditi's decisions on Q1 to Q15 are consolidated into `SPEC.md`, each in the decisions register with assumptions, implementation, validation test and failure behavior. Every config value is classified by basis in `config/parameters.yaml`. The code for the decisions that touch existing modules is built: limit orders, execution-grade quotes, the execution window, pending orders, license tags, record types, the UNKNOWN sector bucket, deterioration monitoring, the promotion check and academic evidence with an implementation gap.

Full suite: 170 passed. Details in `TEST_RESULTS.md`.

## Half done

- **The Composite has no real inputs.** Everything in section C runs on synthetic data. Nothing connects it to the point-in-time store yet, because there is no real price history and no Level A signal. That wiring is Phase 1 and Phase 3 work.

## Not started

- Phase 1 and later. No network call, broker account or UI exists.
- `SOURCE_REGISTRY.md`, `RESEARCH_PROTOCOL.md`, `DESIGN_SYSTEM.md`.

## Commands

```bash
make setup
```

```bash
make ci
```

```bash
make phase0
```

## Known flaws

- The risk engine runs in-process. The spec wants a separate process. The message types are ready for that move (DECISIONS D-007).
- The daily loss stop blocks buys and allows sells that reduce risk (DECISIONS D-009). Aditi should confirm.
- The cluster mapping for the 20% limit does not exist. Callers supply cluster labels, and a missing one blocks the book.
- The optimizer has only been run on books of 40 to 60 names. Speed at about 3,000 names is unknown.
- The Composite's volatility bisection stops within 1% under the target, and HRP uses single linkage. Both are reasonable defaults and neither is in config yet.
- Tests ran on Python 3.13 only.
- Some review facts are still unverified. They are listed in `REVIEW.md` section 5.

## Exact next step

Start Phase 1 (US paper vertical slice). First atomic task: the survivorship-aware forward recorder, because every day it runs adds prospective history. Build `candleisgreen/sources/alpaca_recorder.py` against recorded API fixtures first, with no network: it stores the full asset list including inactive assets, daily consolidated bars requested at least 15 minutes after the close, and corporate actions, and writes a completeness flag per day. Tests: a delisted name stays in the instrument master with its date, a missed day is flagged, a ticker change keeps one `instrument_id`, and running the job twice stores the same result. While building it, check whether Alpaca serves bars for delisted symbols (spec decision Q1 assumption). Then the Oracle heartbeat and local fallback (Q13), then the Level A trend baseline.

Alpaca paper keys are needed for any live call. They come from environment variables only, and only the paper endpoint is allowed.
