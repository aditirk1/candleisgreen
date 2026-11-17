# HANDOFF.md

Last updated: 2026-11-17 09:27 ET. Branch: `spec-review-and-phase0`. Draft pull request: https://github.com/aditirk1/candleisgreen/pull/1

## Timeline note

The overnight run stopped at about 01:35 ET when the usage limit was reached, so no checkpoint was written at 02:40 ET. Everything up to Phase 0 had been committed and pushed by then. Work resumed at 09:21 ET and the Composite was finished and committed after that.

## Done

1. **Review pass.** `REVIEW.md`: errors (E1 to E30), outdated facts, disagreements, open questions, each with a verification status.
2. **Spec v3.1.** `SPEC.md` has every technical fix from the review applied, with a change log at the end. Hard risk limits were not changed. Decisions that need Aditi are in `QUESTIONS.md`, each with the default now in use.
3. **Documents.** `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RISK_POLICY.md`, `MODEL_REGISTRY.md`, `DECISIONS.md`, `TEST_RESULTS.md`, `README.md`.
4. **Phase 0.** Both acceptance tests pass: one offline event flows end to end with immutable IDs, and a planted lookahead leak is caught.
5. **Composite module.** `candleisgreen/composite/` covers C.2 and C.4 to C.10, plus `risk.engine.evaluate_portfolio` for the independent book check. Every C.12 test passes on synthetic inputs.

Full suite: 111 passed. Details in `TEST_RESULTS.md`.

## Half done

- **C.3 research portfolio builder.** Not built. It should turn smoothed z-scores and daily returns into each signal's daily net return series: dollar-neutral weights for cross-sectional signals, directional for time-series, scaled to 10% ex-ante volatility, costs from the cost model at actual turnover, plus the long-only top-tercile series for the Tier 4 test. Today `composite/run.py` takes these series as inputs.
- **Cost model.** Defined in SPEC C.3. Not in code. The SEC and FINRA fee rates and a borrow rate need config keys.

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

Build `candleisgreen/composite/research_portfolio.py` (spec C.3) with the cost model: input T x N smoothed z-scores, T x N next-day asset returns, the factor model, quotes and ADV, config. Output daily gross and net returns, daily cost, turnover, and the long-only top-tercile series. Test it by feeding a signal with a planted known edge and checking that `annualized_mean_and_se` recovers it, then pass its output into `run.daily` in place of the synthetic `returns` used in `tests/test_composite_c12.py`. After that, Phase 1 (US paper vertical slice) per `SPEC.md`.
