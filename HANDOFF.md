# HANDOFF.md

Last updated: 2026-11-17 09:31 ET. Branch: `spec-review-and-phase0`. Draft pull request: https://github.com/aditirk1/candleisgreen/pull/1

## Timeline note

The overnight run stopped at about 01:35 ET when the usage limit was reached, so no checkpoint was written at 02:40 ET. Everything up to Phase 0 had been committed and pushed by then. Work resumed at 09:21 ET and the Composite was finished and committed after that.

## Done

1. **Review pass.** `REVIEW.md`: errors (E1 to E30), outdated facts, disagreements, open questions, each with a verification status.
2. **Spec v3.1.** `SPEC.md` has every technical fix from the review applied, with a change log at the end. Hard risk limits were not changed. Decisions that need Aditi are in `QUESTIONS.md`, each with the default now in use.
3. **Documents.** `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RISK_POLICY.md`, `MODEL_REGISTRY.md`, `DECISIONS.md`, `TEST_RESULTS.md`, `README.md`.
4. **Phase 0.** Both acceptance tests pass: one offline event flows end to end with immutable IDs, and a planted lookahead leak is caught.
5. **Composite module.** `candleisgreen/composite/` covers all of spec section C: research portfolios and the cost model (C.3), standardization (C.2), edge estimation (C.4), eligibility with the Tier 3 and Tier 4 gates (C.5), weights (C.6), score, α and calibration (C.7), factor model and optimizer (C.8), and the daily run record (C.10). `risk.engine.evaluate_portfolio` gives the independent book check. Every C.12 test passes on synthetic inputs.

Full suite: 119 passed. Details in `TEST_RESULTS.md`.

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

Start Phase 1 (US paper vertical slice) per `SPEC.md`. The first atomic task: write `candleisgreen/models/ts_momentum.py`, the Level A trend baseline `ts_momentum_252_21` from `MODEL_REGISTRY.md` section 4. It reads daily closes through `PointInTimeStore.as_of`, outputs `signal_strength` per asset, and calls `assert_no_lookahead`. Test it on a new multi-day fixture in `tests/fixtures/`, then route its forecast through the existing `pipeline.py` path in place of `fixture_baseline`. Alpaca stays out until the fixture path passes, and only paper endpoints are allowed.

Phase 1 should also start the forward recorder early (spec Phase 1 scope, `QUESTIONS.md` Q1). Edge is judged on free portfolio returns from day one, and the recorder feeds the 63-day Tier 5 shadow that comes before any paper position. Daily bars come from Alpaca's consolidated history, requested at least 15 minutes after the close. Check `config/capabilities.yaml` before building anything that touches options, intraday data or analyst estimates: those are NOT AVAILABLE. Standing rule: no subscription or monthly fee, ever. Before Phase 1, Aditi should skim `QUESTIONS.md`. Q1 (free data plan), Q4 (execution timing), Q13 (jobs on her computer) and D-009 in `DECISIONS.md` (daily loss stop and sells) change what Phase 1 builds.
