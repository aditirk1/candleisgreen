# HANDOFF.md

Last updated: 2026-11-24 01:35 ET. Branch: `spec-review-and-phase0`. Draft pull request: https://github.com/aditirk1/candleisgreen/pull/1

## Timeline note

The overnight run stopped at about 01:35 ET when the usage limit was reached, so no checkpoint was written at 02:40 ET. Everything up to Phase 0 had been committed and pushed by then. Work resumed at 09:21 ET and the Composite was finished and committed after that.

## Done

1. **Review pass.** `REVIEW.md`: errors (E1 to E30), outdated facts, disagreements, open questions, each with a verification status.
2. **Spec v3.1.** `SPEC.md` has every technical fix from the review applied, with a change log at the end. Hard risk limits were not changed. Decisions that need Aditi are in `QUESTIONS.md`, each with the default now in use.
3. **Documents.** `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RISK_POLICY.md`, `MODEL_REGISTRY.md`, `DECISIONS.md`, `TEST_RESULTS.md`, `README.md`.
4. **Phase 0.** Both acceptance tests pass: one offline event flows end to end with immutable IDs, and a planted lookahead leak is caught.
5. **Composite module.** `candleisgreen/composite/` covers all of spec section C: research portfolios and the cost model (C.3), standardization (C.2), edge estimation (C.4), eligibility with the Tier 3 and Tier 4 gates (C.5), weights (C.6), score, α and calibration (C.7), factor model and optimizer (C.8), and the daily run record (C.10). `risk.engine.evaluate_portfolio` gives the independent book check. Every C.12 test passes on synthetic inputs.

6. **Spec v3.2.** Aditi's decisions on Q1 to Q15 are consolidated into `SPEC.md`, each in the decisions register with assumptions, implementation, validation test and failure behavior. Every config value is classified by basis in `config/parameters.yaml`. The code for the decisions that touch existing modules is built: limit orders, execution-grade quotes, the execution window, pending orders, license tags, record types, the UNKNOWN sector bucket, deterioration monitoring, the promotion check and academic evidence with an implementation gap.

7. **Phase 1, US paper vertical slice.** Acceptance test passed. Survivorship-aware recorder against an offline synthetic Alpaca market, split and dividend adjustment, decision-time universe, the Level A trend baseline (Tier 1, simulator only), an audited journal, the risk service as its own process owning the kill switch, the decision and next-session executor with limit orders, scheduled jobs with heartbeat and fallback, the workstation API, and the Overview and Execution screens in React. Screens verified with Playwright.

8. **Phase 2, broker paper and filings.** Acceptance test passed. Alpaca paper adapter with duplicate safety and reconciliation that fails closed, SEC filings and XBRL facts timestamped at acceptance with restatements as vintages, Fama-French 12 classifications with mapping version and date, the earnings scorecard with no beat or miss, slippage by window, and the Earnings screen.

9. **Phase 3, research engine and the first Composite.** Acceptance test passed. Experiment registry with frozen pre-registered plans, trial counts and a failure archive, claim cards and an evidence graph, reproduction and replication on real Open Source Asset Pricing returns (momentum passes, betting against beta fails as expected), cross-sectional momentum and short-term reversal baselines, Composite v0 through every step with each signal's evidence chain, and the Research and Composite screens.

10. **Phase 4, news and teaching.** Acceptance test passed. Lawful RSS from official feeds with safe parsing and story clustering, the News, Reasoning and Learn screens, predict-first with Brier scoring and calibration, and an as-known-then replay that cannot see later news, prices or corrections.

11. **Phase 5, Hypothesis Factory and model levels B and C.** Acceptance test passed. Daily factory with duplicate, novelty and data checks and a digest, decision rules by study type, re-evaluation cases, Aditi-only promotion above Tier 4, drift monitoring, practitioner scoring, and ridge and boosted-tree models compared out of sample.
12. **Phase 6, global research.** Acceptance test passed. Instrument taxonomy with a risk check that blocks non-US instruments, a market rule table from official sources, the NYSE calendar, FRED FX with the local and FX split, JKP momentum evidence by market, follow-the-sun scheduling on APScheduler, and the Global screen.

Full suite: 274 passed. Details in `TEST_RESULTS.md`. Phase 7 (live trading) is not started and needs a separate written decision from Aditi.

## Half done

- **Live Alpaca data.** The client is written from Alpaca's documentation and tested offline. The first run with paper keys must compare response shapes (DECISIONS D-033), and check whether bars for delisted symbols are served (spec decision Q1).
- **The Composite does not trade yet.** No signal holds Tier 4, so the Composite allocates nothing and the trading loop still runs the single Level A baseline in the simulator. That changes only when an executable approximation passes on real data.

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

Phase 5 (Hypothesis Factory and model levels B and C). First atomic task: `candleisgreen/research/factory.py`, the daily research loop that turns new claim cards into pre-registered experiments, checks novelty against the signal library, marks NEEDS_DATA with the missing dataset, and publishes a daily digest. Then champion and challenger tracking, drift monitoring wired to the deterioration test, practitioner claim scoring, and a re-evaluation case when a new paper contradicts an active signal. Acceptance: a model update never changes risk limits or permissions, and a contradicting paper opens a re-evaluation case.

Commands:

```bash
make ci
```

```bash
make demo
```
