# HANDOFF.md

Last updated: 2026-11-24 01:50 ET. Branch: `spec-review-and-phase0`. Draft pull request: https://github.com/aditirk1/candleisgreen/pull/1

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

13. **Safety extras.** Hard-limit changes through the risk service (tighten now, loosen after 24 hours with Aditi's confirmation) and a pre-open check that only cancels risky buys.
14. **All fifteen screens.** Opportunities, Markets, Experts, Backtests, Audit and Rules, and Settings join the earlier nine. Command bar with coded commands and plain phrases, Guide mode with plain labels and hover definitions, Explain this screen, and a first-run tour.
15. **Correlation clusters.** Monthly residual-return clustering with a stability test, sector fallback when unstable, and the executor counting exposure per cluster.
16. **Research Capture Inbox.** On the Research screen. Stores a hash, the time and a short summary, extracts testable claims and forecasts into claim cards for the nightly research loop, and asks for the passage when a link or file cannot be read.
17. **Macro vintages.** FRED API `series/observations` over the full real-time period, every revision stored as a vintage, usable from 17:00 New York time on its release date, shown on the Global screen. NOT AVAILABLE without a key.
18. **Clinical trials.** Forward snapshots from the ClinicalTrials.gov API v2 for names with biotech SIC codes, linked only on an exact lead-sponsor match to the SEC entity name. Changes between snapshots become trial events. Shown on Markets. Trial data is research only by license.
19. **Teaching tools.** Market autopsy for each simulated fill, a counterfactual that runs the real trend model and risk limit and is labeled HYPOTHETICAL, spaced review with wrong predictions first and replay outcomes kept hidden, and a crisis library that stays NOT AVAILABLE until stored data covers each episode. The glossary now lives in `config/glossary.json`, shared by Guide mode and the review deck.
20. **Scheduled trading day and Tier 5 shadow tracking.** The scheduler now runs the decision at 16:30, execution at 09:35 and expiry at 10:30, all in New York time, with execution through the risk service process. The daily Composite run follows the decision, and any Tier 4 signal gets a prospective shadow book whose `promotion_check` pass opens a proposal only Aditi can decide. Execution quotes come from Alpaca's free IEX latest quotes and the paper clock.
21. **Concept map and daily lesson.** Glossary terms carry prerequisites, the Learn screen lists them in learning order, and one lesson a day uses the largest recorded move on the latest session, with its source and the time it became known.
22. **Experiment lab.** A plain-words idea becomes a null hypothesis, a data plan with free substitutes for missing data, and a holdout test rule, then is pre-registered through the same factory as a paper. The server redesigns the idea on submit, so the stored plan is exactly what the rules produce.
23. **Interface redesign.** Light theme, grouped sidebar, a calmer front page (key numbers, next session plan, top stories, holdings), opportunity rows that open their evidence, Learn and Research in tabs, and a stock panel for any ticker. News cards give the source summary, why that kind of news can matter, the companies named, and what their prices did next, with market-relevant stories first.
24. **Short selling, on.** Built through the decision, risk service, executor, pre-open check and screens. Aditi set 3% per stock and 30% in total on 2026-11-27 and waived the 24-hour wait once. The Short selling card on Audit and Rules turns it off at once, and turning it back on waits 24 hours. Options, crypto and futures stay off, with reasons in the capability map.

Full suite: 346 passed. Playwright: 84 checks. Details in `TEST_RESULTS.md`. Phase 7 (live trading) is not started and needs a separate written decision from Aditi.

## Half done

- **Live FRED macro.** Built against the documented response shape with a constructed fixture. The first run with a key in `FRED_API_KEY` must compare shapes and check how missing values appear.
- **Live Alpaca quotes and clock.** `sources/alpaca_quotes.py` follows the documented latest-quotes and clock responses and runs offline against the fake market. The first run with paper keys must compare shapes.
- **Live Alpaca data.** The client is written from Alpaca's documentation and tested offline. The first run with paper keys must compare response shapes (DECISIONS D-033), and check whether bars for delisted symbols are served (spec decision Q1).
- **The Composite does not trade yet.** No signal holds Tier 4, so the Composite allocates nothing and the trading loop still runs the single Level A baseline. The Composite now runs daily after the decision and any Tier 4 signal starts a shadow book at once. Promotion to Tier 5 then needs `promotion_check` and Aditi.

## Not started

- Phase 7 (live trading). Needs a separate written decision from Aditi.
- FDA advisory committee calendar. NOT AVAILABLE: the FDA page fills its table with JavaScript and has no documented feed. Meeting notices can be pasted into the Research Capture Inbox. FDA action dates must come from press releases and 8-K filings.
- Read the ClinicalTrials.gov terms by hand. The page renders with JavaScript and could not be read automatically.
- Teaching: a fuller decision reconstruction than the Reasoning screen gives.
- Tier 5 shadow tracking process for a Composite signal that reaches Tier 4.

## Commands

```bash
make setup
```

```bash
make ci
```

```bash
make demo
```

```bash
make screens
```

## Known flaws

- The daily loss stop blocks buys and allows sells that reduce risk (DECISIONS D-009). Aditi should confirm.
- The optimizer has only been run on books of 40 to 60 names. Speed at about 3,000 names is unknown.
- The Composite's volatility bisection stops within 1% under the target, and HRP uses single linkage. Neither is in config yet.
- The watchlist lives in browser storage only.
- Tests ran on Python 3.13 only.
- Some review facts are still unverified. They are listed in `REVIEW.md` section 5.

## Exact next step

Run the scheduler for a week against real Alpaca paper data and the free IEX quotes once keys exist, and compare response shapes (quotes, clock, bars).
