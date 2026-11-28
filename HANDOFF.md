# HANDOFF.md

Last updated: 2026-11-27. Working branch: `ux-redesign-intelligence`, draft pull request https://github.com/aditirk1/candleisgreen/pull/2, based on `spec-review-and-phase0` (draft pull request https://github.com/aditirk1/candleisgreen/pull/1).

## Options, crypto, forex and futures (branch `multi-asset-research`, based on `ux-redesign-intelligence`)

Each asset class now records eight levels in `config/capabilities.yaml` (entries `asset_*`), shown on Markets, Asset classes. Live trading is never built. No broker order is sent for any of the four new asset classes.

### PR #3 review fixes, 2026-11-28

| Review item | What changed | Tested by |
| --- | --- | --- |
| 1. Crypto book freshness | A book with no time, an unreadable time, an age over 15 seconds or a time over 2 seconds in the future is refused. New safeguards `assets.crypto.risk.max_book_age_seconds` and `max_clock_skew_seconds` | `tests/test_crypto.py`, and live: the real Alpaca book passed the check through the app's routes |
| 2. Crypto practice persistence | `markets/crypto_ledger.py`: append-only SQLite ledger, one insert per order with the account state after it. Each row names the row before it uniquely, so two writers cannot fork the balance. A repeated client order ID returns the first result. A reused ID for a different order is refused. Fee tier volume counts only the last 30 days | Restart recovery, duplicate, reuse, two-writer and stale-writer tests |
| 3. Options audit | Early assignment: new safeguard `require_cash_for_early_assignment` needs the cash an early assignment would take, and every strategy with a short leg carries a disclosure that dividend dates are not recorded. Dividends: the model is Black-Scholes-Merton with a dividend yield and says it is European. Multi-leg: a net limit is required and all legs fill together or none. Separation: simulated fills record `executable=False`, and the order builder refuses any leg without an executable quote | `tests/test_options.py` |
| 4. Futures data | CFTC rows validated before storage (market code, futures only, Tuesday date, fields present). Settlement uploads need a source and a license confirmation, positive prices, past dates, no conflicting duplicates. Each contract term records a CME check date. Contract sizes cross-checked against the CFTC record (all five match). The simulator trades only confirmed sizes. Calendar and rolls labeled estimates | `tests/test_futures.py` on real CFTC reports, live CFTC check |
| 5. CI | `.github/workflows/ci.yml`: Python tests, frontend type check and build, Playwright on fresh demo data through `scripts/ci_playwright.sh`. Playwright 1.63.0 added as an exact dev dependency. Free tools only | The same steps ran locally: clean `npm ci`, type check, build, 125 browser checks passed |
| 6. Live checks | Six live checks passed on 2026-11-28. Every run prints how many passed tests used live calls, real recorded responses, documented shapes with invented values, or offline logic | See `TEST_RESULTS.md` |

Still not verified against a live service: Alpaca options, Alpaca stocks, OANDA (need your credentials), CME (site did not answer), Kraken (license unconfirmed).

### Where each asset class stands

| Level | Options | Crypto | Forex | Futures |
| --- | --- | --- | --- | --- |
| Free source exists | Yes, Alpaca indicative feed | Yes, Alpaca. Kraken as comparison | Yes, OANDA practice, FRED | Partly. CFTC positioning yes, CME terms unread |
| Adapter built | Yes | Yes. Kraken blocked by license | Yes, read only, no order methods | Partly. CFTC yes, CME no |
| History checked live | Waiting for Alpaca keys | Yes, 2026-11-28, BTC/USD from 2021-01-01 | Waiting for OANDA token | Partly. CFTC checked 2026-11-28. No prices |
| Current prices checked live | Waiting for Alpaca keys | Yes, 2026-11-28, order book | Waiting for OANDA token | No free source |
| Research | Partly. Payoff calculator and model work, chain needs keys | Yes | Partly. FRED rates now, spreads need OANDA | Partly. Positioning, contract calendar, rolls, continuous series on uploads |
| Simulation | Yes | Yes | Waiting. Built, runs on OANDA prices | Partly. Daily simulator on uploads, margins entered by hand |
| Broker paper trading | Waiting. Order builder done, nothing sends it | No. Needs keys and a read-only check first | No | No. Alpaca lists futures as coming soon |
| Live trading | No | No | No | No |

### Completed and tested

- Options (`candleisgreen/markets/options.py`, `options_sim.py`, `sources/alpaca_options.py`): OCC symbols, exact payoff profiles with break-evens, labeled Black-Scholes values, expiry exercise and assignment on Alpaca's rule, risk checks, a simulator labeled indicative, a read-only client that refuses OPRA, an order builder in Alpaca's documented shape. `tests/test_options.py` (12).
- Crypto (`markets/crypto.py`, `sources/alpaca_crypto.py`, `sources/kraken.py`): fees from Alpaca's published tiers, order book spread and depth, risk checks with no shorts and no margin, a simulator that walks the book. `tests/test_crypto.py` (10).
- Forex (`markets/forex.py`, `sources/oanda.py`): practice host only, daily candles ending 17:00 New York across daylight saving, spreads from bid and ask, size and leverage checks, a simulator. `tests/test_forex.py` (7).
- Futures (`markets/futures.py`, `sources/cftc.py`, `config/futures_contracts.yaml`): last trading and first notice rules, rolls, three continuous series methods, a daily simulator with margin calls, CFTC positioning with conservative usable times. `tests/test_futures.py` (9), on real CFTC reports.
- Shared: `markets/store.py` (point-in-time store, separate from stocks), `sources/public_http.py` (read-only, host allowlist), `markets/service.py` (recording jobs), `api/assets.py` (routes), registry and API tests in `tests/test_asset_levels.py` (6).
- Live checks in `tests/test_live_sources.py`, skipped unless `CANDLE_LIVE=1`. Crypto and CFTC passed on 2026-11-28. Options and OANDA wait for credentials.

`make ci`: 412 passed, 8 skipped (the live checks). Playwright: 125 checks passed, including Focus-mode guards on every asset class view.

### Waiting on you

1. Alpaca paper keys (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`): turns on the options chain and the options and stock live checks. Then run `CANDLE_LIVE=1 .venv/bin/python -m pytest tests/test_live_sources.py -v`.
2. OANDA: open a free fxTrade Practice account, create a token, set `OANDA_PRACTICE_TOKEN` and `OANDA_PRACTICE_ACCOUNT_ID`. Read the API license shown when you create the token. If it allows personal research, set `oanda_practice` research to `permitted` in `config/licenses.yaml`.
3. Kraken (optional): read sections 8 and 9 of kraken.com/legal/global-terms. Only if they allow this use, set `kraken_public` research to `permitted`.
4. CME: open the five contract specification pages linked in `config/futures_contracts.yaml`, compare each term, and put the date in that term's `checked_against_cme` entry. Calendar results stop being labeled estimates once months and both date rules are checked.
5. GitHub Actions: the workflow runs on free minutes. If the repository is private and the free minutes run out, runs pause until the next month. Nothing is charged unless you add a payment method.

### Commands

```
.venv/bin/python -m candleisgreen.markets.service crypto --workdir var/live
.venv/bin/python -m candleisgreen.markets.service cot --workdir var/live
```

Both need only an internet connection. The app's Record latest and Read latest reports buttons do the same.

### Known flaws

- Forex and options simulators have no screen for placing practice orders yet. Their code is tested directly.
- The holiday list covers 2026 and 2027 only, so futures dates after 2027 are refused.
- Exchange holidays use the NYSE list. CME holidays mostly match it but are not checked.

### Next steps

1. With keys: run the live checks, then build Alpaca paper crypto orders through the independent risk service, with the crypto checks added there.
2. With an OANDA token: record candles, fit the spread model, run the forex simulator on real bid and ask.
3. Keep options broker orders off until Aditi decides how indicative quotes relate to the execution-grade quote rule.

## UX redesign and financial intelligence upgrade (branch `ux-redesign-intelligence`)

### Completed and tested

| Priority | What is built | Tested by |
| --- | --- | --- |
| 1. Information architecture | Six destinations (Home, Discover, Markets, Intelligence, Portfolio, Learn), Research workspace and Settings below a divider, contextual tabs, Focus (default) and Advanced modes, back and forward through the URL hash. Every earlier screen and command still works | Playwright: navigation through every destination and tab, command bar |
| 2. Themes | Light and Dark from one token set (type, surfaces, borders, text, accent, gain and loss, warning, charts, hover). Light has no gradients or translucency. Charts redraw on a switch. Choice saved in the browser | Playwright: light background value, charts drawn in both themes, 14 principal screenshots in both themes |
| 3. Market intelligence | Story cards with source summary or an explicit "excerpt only repeats the headline", source and timestamps per item, companies and industries, why it may matter, labeled hypotheses, measured price reaction, portfolio relevance. Documented relevance score, MATERIAL or ROUTINE, relevance or recency sort, headline search, category, industry, watchlist and saved filters, read and save marks. Templated headlines about different events no longer merge | `tests/test_news_insight.py` (9), Playwright news checks |
| 4. Home | Demo or live data banner, account value, profit and loss, invested capital, account and market status, performance chart with ranges and an empty state, Needs Attention, material developments, top opportunities, watchlist, positions, folded System Health. Kill switch in the top bar | `/api/home` in tests, Playwright Home checks |
| 5. Opportunities | Compact table with signal strength, one month and one year change, and in Advanced volatility, trading volume and tier. Ticker or row opens an evidence drawer: conclusion, horizon, model reasoning, supporting and opposing signals, risk checks and uncertainty, news and catalysts, provenance, links to Reasoning, Research and the company page. Keyboard: focus in, Tab trapped, Escape closes, focus returns | Playwright drawer checks by keyboard |
| 6. Company pages | Markets, Company tab. SEC profile, financials from XBRL with filing links, period and age in days, price to earnings only with sourced inputs, measured risks, recorded catalysts, news, candles with volume, trade or abstain reason | `tests/test_company.py` (3), Playwright company checks |
| 7. Asset classes | Markets, Asset classes tab. Stocks and ETFs, options, futures, forex, crypto from `config/asset_classes.yaml` and the capability registry | `tests/test_asset_classes.py` (2), Playwright |
| 8. Ownership intelligence | Form 4 insider transactions (transaction and disclosure dates apart, 10b5-1 flag, codes explained), 13F holdings (summed per security, quarter end and filing apart, limits stated), Schedule 13D and 13G filing dates. Research only. Overnight refresh when `SEC_USER_AGENT` is set. Intelligence, Insiders and institutions tab | `tests/test_ownership.py` (3) on real SEC filings, Playwright |

Also: candlestick charts with volume and ranges everywhere prices are shown (`/api/bars`), the Home crash on blocked orders fixed earlier, and demo candles that open at the prior close.

Plain language pass (D-127 to D-129): every screen, the Research workspace tabs and the evidence drawer show plain names instead of code names (for example "Momentum, 12-month winners against losers" for `xs_momentum_12_1`, "Largest position, share of account" for `max_position_pct_equity`). Reasons from the backend are rewritten in `ui/src/labels.ts`. IDs, hashes, versions and config paths moved into Advanced mode's "Technical details". The API is unchanged.

`make ci`: 357 passed. Frontend production build passes. Playwright: 114 checks passed, including a guard that Focus mode shows no code names, config paths, record IDs or hashes.

### Unavailable, with the reason shown in the app

| Capability | Why |
| --- | --- |
| Options, futures, crypto and forex trading | Options: only an indicative free feed, which fails the execution-grade quote rule. Futures: not offered by Alpaca, other sources charge. Crypto: free data exists, not built. Forex: Alpaca offers no currency trading |
| Option Greeks, futures quotes | No data source. Nothing is computed |
| Congressional disclosures | Not built. Disclosure up to 45 days late, many scanned reports, source terms unchecked |
| Government procurement, regulatory actions beyond News | Not built. USAspending.gov and the Federal Register need their terms and formats checked |
| Political sector exposure | Not built. Needs classified companies and a pre-registered event study |
| Revenue model, 10-K business description and risk factors | Not parsed. The page uses the SEC industry code description and says so |
| Price to book, price to sales | Shares outstanding are not collected |
| Earnings calendar | No free source |
| CUSIP to ticker mapping for 13F holdings | No free CUSIP map |
| Holder and stake inside 13D and 13G filings | Not parsed yet |

### Next steps

1. Run against live data once keys exist (Alpaca paper keys, `SEC_USER_AGENT`, `FRED_API_KEY`) and compare response shapes.
2. Collect shares outstanding (XBRL `dei:EntityCommonStockSharesOutstanding`) so price to book and price to sales can be shown.
3. Pre-register a test of open-market insider purchases (code P, not 10b5-1) before anything is built on them.

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
