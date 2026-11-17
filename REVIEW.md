# REVIEW.md: review pass on Build Spec v3

Reviewed 2026-11-17 against `spec.md` (v3, dated Nov 16, 2026).

## How this review was done

- Web facts were checked by research subagents against official pages on 2026-11-17. Each finding carries a status: VERIFIED (read on a primary page), SNIPPET (seen only in search results because the page blocked fetches), or UNVERIFIED (not reached or not confirmable).
- The research agents were cut short by a usage limit, so some items were not reached in the first pass. A follow-up pass covers them. Anything still open is listed in section 5.
- Formulas in the Composite section were recomputed by hand and in a scratch script. The numbers quoted under each finding come from that script.
- Hard risk limits are not changed anywhere in this review. Where a hard limit conflicts with another rule, the other rule is changed.
- IDs: E = error, O = outdated fact, D = disagreement with a proposed change, Q = open question.

Each item ends with **Change**, which is what spec v3.1 does about it.

---

## 1. Errors

### Formulas and internal contradictions in the Composite

**E1. The worked example (C.11) contradicts the eligibility rule (C.5).**
The arithmetic in C.11 is right (edge 2.63%, sd 1.44%, P 0.966, and 0.40% / P 0.571 for the noise case). The conclusion is wrong. C.5 needs Tier 4, and Tier 4 needs the lower bound of the 90% interval of net return above zero. The example's out-of-sample record is 2.0% with standard error 2.5%, so t = 0.8 and the lower bound is about -2.1%. That signal cannot be Tier 4, so it is not eligible.
**Change:** the example now uses an out-of-sample record of 5.0% with standard error 2.5% (t = 2.0), which passes Tier 4, and states both gates.

**E2. The P ≥ 0.80 gate cannot deliver the C.12 test "pure noise excluded in at least 95% of runs".**
For a signal with no paper, P ≥ 0.80 needs t ≥ 0.8416 × sqrt(1 + σ²/τ²). A zero-edge signal passes that 3.0% of the time with 1 year of record, 7.2% with 2 years, 11.7% with 4 years, 17.3% with 16 years, and 20% in the limit. The 95% exclusion only holds because of the Tier 4 gate.
**Change:** C.12 now states the test on the joint gate (Tier 4 economic test and P ≥ 0.80). The 0.80 default stays. See D1 for the option of raising it.

**E30. The Tier 4 test alone meets the 95% noise bar with no margin.** Found while building the C.12 tests on 2026-11-17. The economic test is a one-sided 5% test, so it admits about 5% of zero-edge signals (measured: 4.9% at 2000 resamples, 5.7% at 300). A C.12 test that checks Tier 4 alone against "excluded in at least 95%" passes or fails on the random seed. The bar holds with margin only because Tier 4 sits behind Tier 3, an independent replication significant at 5%.
**Change:** C.12 now tests the full path (Tier 3, Tier 4, P\_s). A separate test pins the Tier 4 rate near 5%. The Tier 3 significance level is a config value.

**E3. For published signals the P gate depends almost only on the paper, and δ cancels out.**
With paper evidence alone, μ̂/√V = t_paper / sqrt(1 + 0.25 t_paper²). δ appears in numerator and denominator and drops out. Any paper with in-sample t above 0.93 gives P ≥ 0.80, and P can never exceed 0.977. A published signal with a one-year out-of-sample record of -10% still shows P = 0.93. This is by construction of ω = 0.5 × δ × R.
**Change:** documented in C.4 as a known property. The Tier 4 gate is named as the binding test for published signals. No formula change.

**E4. Paper returns are gross, platform returns are net.**
C.4 combines R_paper (gross, usually decile sorts on the full CRSP universe) with r̄_s (net of costs, z-score weights, filtered universe, long-short). They measure different things, and the precision-weighted mean treats them as the same quantity.
**Change:** the paper measurement is now δ_k × R_paper minus the platform's modeled annual cost for that signal at 10% volatility. SE_paper is rescaled to 10% volatility in the same way as R_paper.

**E5. The family prior double counts.**
m_k is built from the family's r̄_s, including the signal being scored, and is then combined with that signal's own r̄_s as if independent.
**Change:** m_k and τ_k for signal s are computed leaving s out.

**E6. σ_s is used for two different things.**
C.3 defines σ_s as the standard error of the mean return. C.6 step 1 then uses w ∝ μ̂_s / σ_s² as the one-or-two-signal fallback for Σ⁻¹μ̂. Every signal is scaled to 10% volatility, so the diagonal case of Σ⁻¹μ̂ is w ∝ μ̂_s. Using the standard error instead weights by length of history.
**Change:** the fallback is w ∝ μ̂_s / v_s, where v_s is the realized return variance of signal s. The standard error keeps the name σ_s.

**E7. ω means two things.** It is the uncertainty term in C.4 and the final signal weight in C.6.
**Change:** final weights are now written w_s. ω stays for the uncertainty term.

**E8. The caps in C.6 are infeasible for a small Composite.**
A 20% signal cap needs at least 5 signals. A 35% family cap needs at least 3 families. Phase 3 asks for "Composite v0 over three Level A signals", where the caps allow at most 60% total weight, and the redistribution loop never ends.
**Change:** weights may sum to less than 1. When caps cannot be met, the unallocated remainder is recorded as `unallocated_weight` and α is scaled by the allocated share. The loop stops when no cap binds or no uncapped signal remains.

**E9. The 25% monthly change limit is relative, so it blocks entries and exits.**
A new signal has prior weight 0 and 25% of 0 is 0. A demoted signal must go to 0 at once, which is a 100% change, and the others must absorb it.
**Change:** the limit is the larger of 25% of the prior weight and 2 percentage points. A new signal enters at no more than 5%. Removal after demotion or feed failure is always immediate and is exempt, and freed weight goes to `unallocated_weight` until the next monthly reweight.

**E10. Signal weights fit on return series are applied to z-scores.**
The w_s are estimated on portfolios scaled to 10% volatility. C.7 applies them to raw z-scores. A z-weighted portfolio has a different native volatility per signal, so the mix that reaches the book differs from the mix that was optimized.
**Change:** S(i,t) = Σ w_s × g_s × z(s,i,t), where g_s is the scale factor that brings signal s to 10% volatility, normalized so the average g_s is 1.

**E11. Smoothing is applied twice, and it leaks event signals outside their window.**
C.2 applies an EMA with half-life h_s/2. C.3 then holds h_s staggered cohorts. Together they roughly double the effective holding period. C.2 item 3 says event signals are zero outside the window, and the EMA in item 4 makes them nonzero after it. C.9 adds a linear decay for practitioner claims, and the EMA would smooth that again.
**Change:** the EMA is the only smoothing. Research portfolios in C.3 rebalance daily to the smoothed z-scores with no cohorts. Event and practitioner signals skip the EMA and are forced to zero outside their window. Scores are re-standardized after smoothing.

**E12. The IC shrinkage makes the calibration check fail by construction for the first two years.**
α uses IC_used = IC_mean × n/(n+252). Regressing realized returns on α over the same record gives a slope of about (n+252)/n: 2.0 at n = 252, 1.67 at 378, and 1.5 only at n = 504. The 0.5 to 1.5 band therefore rejects a perfectly behaved Composite until day 504.
**Change:** the calibration regression uses the unshrunk forecast IC_mean × σ × S. Shrinkage is applied afterwards, to sizing only.

**E13. The IC t-statistic is overstated by overlapping returns.**
Daily observations of 21-day forward returns overlap. A naive t-statistic is too large by up to about sqrt(21) = 4.6.
**Change:** IC statistics use Newey-West errors with lag 21 or non-overlapping 21-day blocks. n in the shrinkage formula stays in days.

**E14. α is a residual-return forecast and the calibration target was total return.**
C.7 defines σ_i and IC on residual returns and then regresses "realized 21-day returns". Time-series signals forecast total return and are mixed into the same score.
**Change:** calibration regresses realized 21-day residual returns. S is demeaned cross-sectionally before the α step. The market-direction content of time-series signals is logged as a separate diagnostic and is not traded in v3.1.

**E15. The optimizer objective mixes units.**
α is a 21-day return, x'Σx has no stated horizon, and costs are one-off. The σ_i inside the impact term must be daily volatility for the square-root law to hold.
**Change:** C.8 states the units. α and Σ are both 21-day quantities. Impact uses daily σ_i and dollar ADV_i. Costs are charged in full against the 21-day α, with a config field for the amortization horizon.

**E16. "λ so that volatility equals 12%" can be unreachable.**
A long-only book with no leverage cannot reach 12% when market volatility is low or when costs outweigh small alphas. Bisection then fails.
**Change:** volatility must be at most the target. If the upper bound of the search still gives less than the target, that solution is accepted and the status is `vol_below_target`.

**E17. Recalibrating κ from paper fills would drive it to zero.**
Alpaca's paper engine fills at the NBBO without checking size and models no market impact (VERIFIED, see O2). Fitting κ to those fills measures nothing.
**Change:** κ has a floor equal to its default. Recalibration from paper or simulated fills can raise κ and can never lower it. Lowering needs real fills, which this project does not have.

**E18. "Ledoit-Wolf shrunk" is undefined for a factor model.**
Ledoit-Wolf shrinks a sample covariance toward a target. A 15-factor model plus specific variance is already a structured estimate.
**Change:** Σ = B F B' + D. F is the Ledoit-Wolf shrunk covariance of the 15 factor returns. D holds specific variances shrunk halfway toward their cross-sectional median. Names with fewer than 126 days of history get the median specific variance and average loadings.

**E19. The "two identical copies" test cannot hold exactly.**
With Ledoit-Wolf shrinkage the pair does not get exactly the weight of one copy. With caps, two copies can hold 40% where one holds 20%. The 1-or-2 signal fallback and Σ⁻¹μ̂ also give different answers.
**Change:** the test allows a tolerance (total weight within 2 percentage points) and runs before caps. The novelty check also merges signals with return correlation above 0.95 into one signal before weighting.

**E20. Newey-West lag h_s degenerates for long horizons.**
A 252-day signal with the minimum 252-day record has a lag equal to the sample length.
**Change:** lag = min(h_s, 63, T/4).

**E21. Tier 5 has no testable definition.**
"Live forecasts land inside the expected range" has almost no power: a zero-edge signal also lands inside a wide range. No shadow length is given.
**Change:** Tier 5 needs at least 63 trading days of shadow forecasts, realized returns inside the pre-registered 90% band, and tracking error between shadow and backtest below a config limit. It is described as an implementation check. The evidence of edge stays at Tier 4.

**E22. The new-factor bar says "t above 3.0, or FDR under 5%".**
"Or" lets the weaker test win, which contradicts "a stricter multiple-testing bar".
**Change:** both are required, plus the holdout.

**E23. First_usable_at has no derivation rule.**
The whole lookahead defense rests on it and the spec never says how it is set. Backfilled history has an ingestion time of today, which would make all history unusable if ingestion time were used.
**Change:** live rows use max(event_time, published_at, vendor_available_at, ingested_at). Backfilled rows use max(event_time, published_at, vendor_available_at) plus a per-source lag from config, and are flagged `collection_mode: backfill`.

### Contradictions outside the Composite

**E24. Opening-auction orders conflict with the safety invariants.**
The risk rules block an order when the market is closed and when the quote is older than 15 seconds. An opening-auction order is sent while the market is closed. Alpaca rejects `opg` orders between 09:28 and 19:00 ET (VERIFIED), and its paper engine is not documented to simulate the auction.
**Change:** v3.1 drops the opening auction. Orders are sliced inside the regular session, 09:35 to 10:30 ET by default, and each slice passes the unchanged risk checks. Alpaca has no VWAP order type (VERIFIED), so slicing is done by the platform.

**E25. The survivorship rule blocks Phase 3 as written.**
Free sources lack delisted stocks. Under the mandatory rule nothing tested on them can pass a gate, so no signal reaches Tier 2 and the Composite stays empty. Phase 3 needs three signals in it.
**Change:** Phase 3 is split. Its acceptance test runs on synthetic and fixture data until survivorship-free data is licensed. Real signals stay labeled SURVIVORSHIP-BIASED and at Tier 1. See D3 and Q1.

**E26. The universe cannot be built from Alpaca alone.**
"US common stocks" needs a security-type field. Alpaca's assets endpoint has none: common stock, ADR, preferred, unit and warrant are not separable (VERIFIED). Sector neutrality needs GICS, which is proprietary with no free point-in-time source (SNIPPET).
**Change:** security type comes from a licensed source or, until then, from SEC form types plus name rules, labeled `type_inferred`. Sectors use SEC SIC codes mapped to Fama-French industries.

**E27. Decision time ignores news between 16:30 and the next open.**
Most earnings arrive after 16:30 or before 09:30. Orders decided at 16:30 are sent the next morning into information the model never saw.
**Change:** a pre-open check at 09:00 ET cancels any buy in a name with an earnings release, halt or 8-K since decision time. It can only cancel orders, never add them.

**E28. File name.** `CLAUDE.md` refers to `SPEC.md`. The file was `spec.md`, which is a different name on Linux.
**Change:** renamed to `SPEC.md`.

**E29. Smaller gaps.**
- The architecture figure is a placeholder ("embedded content") and carries no information. **Change:** replaced by `ARCHITECTURE.md`.
- The cost model is cited as "C.8" but is never defined on its own. Borrow cost for the short leg of research portfolios is missing. **Change:** a cost model subsection is added to C.3 with spread, impact, fees and a borrow rate.
- "Demotion is automatic when a signal fails monitoring" with no monitoring rule. **Change:** see Q6.
- If calibration fails, positions "run to their exits", and the Composite has no exits. **Change:** the optimizer runs in reduce-only mode.
- The universe has no hysteresis, so names near $5 flip in and out daily. **Change:** exit levels of $4 and $7.5M added.
- Leveraged and inverse ETFs would enter the universe. **Change:** excluded by default.
- The crisis library (1987, 1997, 2008) needs data the free sources do not have. Alpaca history starts in 2016. **Change:** those entries show NOT AVAILABLE until data exists.

---

## 2. Outdated facts

**O1. Alpaca "includes real-time market data". QUALIFIED, VERIFIED.**
The free Basic plan gives real-time data from IEX only, a small share of consolidated volume, with 30 websocket symbols and 200 historical calls per minute. Paper-only accounts get IEX only. Full SIP data is Algo Trader Plus at $99 per month. Historical SIP is free only when the request ends at least 15 minutes ago. Sources: https://docs.alpaca.markets/docs/about-market-data-api , https://docs.alpaca.markets/docs/market-data-faq
Effect: the 15-second staleness limit and the 0.5% spread limit will block many names on IEX quotes. That is the correct fail-closed result, and it means the tradable set on the free plan is smaller than the universe.
**Change:** source table updated. Paid SIP stays an open decision (Q2).

**O2. Alpaca paper fills. VERIFIED.**
Paper orders fill at the NBBO without checking quote size, with random partial fills 10% of the time, and no impact, queue position, fees or dividends. Source: https://docs.alpaca.markets/docs/paper-trading
**Change:** the platform's own cost model is applied on top of paper fills in every P&L view, and both numbers are shown.

**O3. Alpaca history and delisted names. VERIFIED and UNVERIFIED parts.**
History starts in 2016 (VERIFIED). There is no historical-assets endpoint (staff statement, Dec 2025). Bars for delisted symbols could not be confirmed. A corporate actions endpoint exists with no stated start date. Source: https://docs.alpaca.markets/reference/stockbars , https://forum.alpaca.markets/t/delisted-tickers/18227
**Change:** Alpaca is named as a price source for live and recent data only. It is not a backtest source.

**O4. Alpaca SDK. VERIFIED.** `alpaca-trade-api` was archived on 2026-06-17. The official SDK is `alpaca-py` (0.45.0). **Change:** named in the stack table.

**O5. Interactive Brokers numbers. SNIPPET.** The current fact sheet reads "over 175 markets in 29 currencies". The spec says 170. IBKR pages blocked direct fetches. A paper account is opened from inside a live account, and real-time data must be shared from the live login. **Change:** text updated to "over 170 market centers", marked as approximate.

**O6. Interactive Brokers Python wrappers. VERIFIED.** `ib_insync` was archived in March 2024. The successor `ib_async` (2.1.0, Dec 2025) has had no release in 11 months. `ibapi` on PyPI is a stale 2020 upload and the official client ships with the IBKR download. **Change:** Phase 6 uses the official TWS API client, with `ib_async` as an option to re-evaluate then.

**O7. Open Source Asset Pricing. VERIFIED with qualifications.**
- Latest data release is dated 2026-10-28 on the site (GitHub tag v2.1.0 is dated 2026-10-27 UTC). 212 predictors. Licence CC BY 4.0. Files moved to Hugging Face.
- The lookahead fix was for AnnouncementReturn in v1.4.1 (2024-10-08).
- Firm-level signals are keyed by CRSP `permno` with no ticker. Mapping them to tradable symbols needs CRSP. Price, Size and STreversal are not in the free firm-level file.
Sources: https://www.openassetpricing.com/ , https://github.com/OpenSourceAP/CrossSection/releases
**Change:** the source table says the free part usable without CRSP is portfolio returns. Firm-level use is NEEDS_DATA.

**O8. JKP Global Factor Data. VERIFIED with qualifications.**
153 factors, 13 themes and 93 countries are confirmed. Free downloads are factor and portfolio returns only. Stock-level characteristics need WRDS with CRSP and Compustat. The data licence is CC BY-NC 4.0, which is non-commercial. Data runs through December 2025. Source: https://jkpfactors.com/data
**Change:** the table states returns only and the non-commercial licence. See Q3.

**O9. Python 3.12. VERIFIED.** 3.12 and 3.13 are security-only. 3.14 and 3.15 are in bugfix. numpy 2.5 and scipy 1.18 need 3.12 or later. 3.15 lacks wheels for cvxpy. **Change:** the stack pins Python 3.14, with 3.12 as the minimum. This container has 3.13, and the code is tested there.

**O10. Library versions. VERIFIED on PyPI and npm.**
| Library | Current | Note for the build |
| --- | --- | --- |
| pandas | 3.1.1 | Copy-on-write always on, `str` dtype, microsecond datetimes, renamed offsets (`ME`, `QE`, `YE`) |
| polars | 2.1.0 | 2.0 shipped 2026-10-06. Breaking changes not reviewed |
| DuckDB | 2.0.0 LTS | 1.4 LTS reached end of life on 2026-11-17 |
| cvxpy | 1.9.3 | Clarabel is the default conic solver. ECOS is no longer bundled. `power(x, 1.5)` defaults to a second-order cone approximation, and `approx=False` gives the exact power cone |
| APScheduler | 3.11.3 | 4.0 is still alpha (4.0.0a6) and its docs say not to use it in production |
| FastAPI | 0.163.1 | Frequent breaking 0.x releases. Pin the exact version |
| Pydantic | 2.14.3 | No v3 |
| statsmodels | 0.15.0 | |
| scikit-learn | 1.9.1 | |
| LightGBM | 4.7.0 | |
| arch | 9.0.0 | Released 2026-11-11 |
| React, TypeScript, Vite | 19.3.1, 7.0.2, 8.3.8 | Create React App is unmaintained. Use Vite |
| AG Grid Community | 36.3.0 | MIT. Enterprise is commercial |
| Lightweight Charts | 5.3.0 | Apache 2.0 |
**Change:** stack table updated. APScheduler is pinned to 3.x.

**O11. OpenAlex. VERIFIED.** It is now usage-priced. A free key gives $1 per day of usage and keyless access covers basic queries. Source: https://help.openalex.org/how-to-use-the-api/rate-limits-and-authentication **Change:** noted in the source table with a daily budget in config.

**O12. Regulatory fees for the cost model.** SEC Section 31 fee is $20.60 per million dollars of sales since 2026-04-04 (VERIFIED, https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2 ). FINRA TAF is $0.00 for 2026-10-01 to 2026-12-31 and is scheduled at $0.000232 per share for 2027 (SNIPPET). **Change:** both are config values in the cost model, applied to sells.

**O13. "FDA calendars" as a free source for biotech events. UNVERIFIED, likely wrong.** FDA publishes an advisory committee calendar. No official FDA calendar of PDUFA goal dates was found. Those dates come from company press releases and 8-K filings. **Change:** the source is restated as ClinicalTrials.gov, the FDA advisory committee calendar, and company 8-Ks for PDUFA dates.

**O14. Polygon.io is now Massive.** polygon.io redirects to massive.com (VERIFIED by redirect). Relevant only to the data options in D3.

**O15. Hosting and AI cost inputs for the README.**
- 2 vCPU, 4 GB server: Hetzner CX23 at EUR 5.99 per month (EU), DigitalOcean $24, AWS Lightsail $24.
- Anthropic list prices per million tokens, input and output: Fable 5.2 $8 and $40, Opus 5.5 $4 and $20, Sonnet 5.5 $2 and $10, Haiku 5.5 $0.10 and $0.50. Batch is 50% off. Source: https://platform.claude.com/docs/en/about-claude/pricing
**Change:** none in the spec. These go in the README cost table when it is written.

**O16. Checked and found correct.**
- McLean and Pontiff: 26% lower out of sample and 58% lower after publication, 97 predictors, long-short returns. VERIFIED. The 0.42 and 0.74 arithmetic is right.
- Jacobs and Müller (2020, JFE): the US is the only country with a reliable post-publication decline. VERIFIED. This supports 0.74 outside the US.
- Harvey, Liu and Zhu: NBER w20592 resolves and argues for t above 3.0. VERIFIED.
- JKP counts, as in O8. VERIFIED.
- Deflated Sharpe ratio (SSRN 2460551) and probability of backtest overfitting (SSRN 2326253): SNIPPET, SSRN blocked fetches.
- SEC EDGAR APIs need no key, with a limit of 10 requests per second and a declared User-Agent. VERIFIED.
- Alpaca paper trading is free, with paper-only accounts and a $100k default balance. VERIFIED.

---

## 3. Disagreements, with proposed changes

**D1. Composite eligibility at P ≥ 0.80.** Keep 0.80. It is weak alone (E2, E3), and the Tier 4 gate does the real work. Raising P to 0.90 would mostly exclude signals with short records and no paper, which Tier 4 already handles. **Change:** none to the number. The joint gate is documented.

**D2. Publication-bias factors 0.42 and 0.74.** The values match McLean and Pontiff. Other estimates differ: Jensen, Kelly and Pedersen find post-sample alpha about 0.53 of in-sample, and Chen and Zimmermann put pure publication bias near 0.88. 0.42 is the conservative end for US signals, which suits a system that should under-trust papers. **Change:** defaults kept. The alternatives are recorded beside them in config comments so the choice is visible.

**D3. Survivorship-free US data.** This is the most important open item, because E25 blocks every real signal until it is settled.

| Option | Delisted stocks | History | Point-in-time fundamentals | Price for an individual | Status |
| --- | --- | --- | --- | --- | --- |
| Sharadar, Bundle Full History | Yes | From about 1998 (start year UNVERIFIED) | Yes, as-reported and indexed to filing date | $69 per month or $499 per year | Price VERIFIED at https://sharadar.com/subscribe . Licence text not read |
| Sharadar, Prices Full History | Yes | Same | No | $39 per month or $299 per year | Price VERIFIED |
| Norgate Platinum | Yes, plus historical index constituents | From 1990 | No | USD 630 per year | VERIFIED at https://norgatedata.com/stockmarketpackages.php |
| Norgate Diamond | Yes | From 1950 | No | USD 787.50 per year | VERIFIED |
| EODHD | Yes | 30+ years | Not point-in-time | $19.99 to $99.99 per month | VERIFIED. Delistings before 2018 have no dividend or split tables |
| Tiingo Power | Not stated | 30+ years | Add-on, price not published | $30 per month | VERIFIED price, coverage unclear |
| Massive (was Polygon) | UNVERIFIED | 20+ years on Advanced | Not point-in-time | $199 per month for Advanced | Partly VERIFIED |
| Databento | UNVERIFIED | About 2018 onward | No | Usage-based | Too short for factor tests |
| Alpaca | Unconfirmed | 2016 onward | No | Free, or $99 per month for SIP | Not a backtest source |
| CRSP through WRDS | Yes, from 1925 | Full | Through Compustat | University access only | See below |

CRSP through Columbia's WRDS access should not be the platform's data layer. The WRDS terms say the service is "for academic and non-commercial research purposes only", and that downloaded data should be deleted when the affiliation ends (VERIFIED, https://wrds-www.wharton.upenn.edu/users/tou/ ). A personal trading platform is outside that, even on paper.

Vendors not reached in this pass: Intrinio, FirstRate Data, Kibot, Algoseek, QuantConnect export terms, CSI Data, Financial Modeling Prep.

**Proposed change:** make Sharadar Bundle Full History the default plan, at $499 per year, after reading its licence terms. It is the only verified option with delisted prices, corporate actions, ETF prices and filing-dated fundamentals at an individual price. Norgate Platinum is the alternative when index membership history matters more than fundamentals. Nothing is bought without Aditi's decision (Q1). Until then the build runs on fixtures and synthetic data.

**D4. Signals are validated long-short and traded long-only.** Much of the published return of equity anomalies sits in the short leg. A signal can pass Tier 4 as a long-short portfolio and add nothing to a long-only book. **Proposed change, applied:** the Tier 4 economic test for a cross-sectional signal has two parts. The long-short test stays as the validity check. The economic value score is measured on the long-only implementation: top-tercile portfolio against the universe return, net of costs. Both are shown, and Tier 4 needs both.

**D5. The benchmark for a 12% volatility long-only book.** With no leverage and a 12% target, the book holds cash whenever market volatility is above about 12%, which is most of the time. Comparing it with fully invested buy and hold mixes skill with the cash position. **Proposed change, applied:** the default benchmark is a mix of a broad US equity ETF and cash rebalanced to the same 12% target.

**D6. Family weights ignore expected return.** Hierarchical risk parity uses risk only, so a family with a tiny edge gets the same budget as a strong one. That is acceptable as a default because edge estimates are noisy. **Change:** none. A challenger that tilts family weights by μ̂ runs in the champion-challenger benchmark.

**D7. Truncating negative weights from Σ⁻¹μ̂.** Setting negatives to zero and rescaling is not the constrained optimum. **Proposed change, applied:** within-family weights solve the non-negative problem directly (minimize w'Σw - 2 w'μ̂ subject to w ≥ 0), then rescale to sum to 1.

**D8. Diebold-Mariano for forecasting models.** The test is not valid when one model nests the other, which is the usual case when a model is compared with its own baseline. **Proposed change, applied:** nested comparisons use the Clark-West test. Non-nested comparisons keep Diebold-Mariano with the Harvey-Leybourne-Newbold correction. The follow-up pass confirmed the nested-model problem from secondary sources, with one caveat: under Giacomini-White assumptions Diebold-Mariano can stay valid for nested models. Clark-West is the safer default.

**D9. Selection cutoff for published signals.** The platform makes its own design choices (horizon, sector neutrality, smoothing) using data after the paper's cutoff. Those choices contaminate the out-of-sample record. **Proposed change, applied:** the cutoff is the latest of the paper's sample end, its first public date, and the date of the platform's last design choice for that signal. Every variant tried counts in the trial registry.

**D10. The other judgment-call defaults.** Reviewed and kept, with notes.

| Default | View |
| --- | --- |
| Cold-start τ = 5% | Keep. It is loose (a 1 sd Sharpe of 0.5), and the paper term dominates it anyway |
| ω factor 0.5 | Keep. It caps paper-only confidence at P = 0.977 (E3) |
| Signal cap 20%, family cap 35% | Keep, with the feasibility rule in E8 |
| Monthly change 25% | Keep, with the floor and exemptions in E9 |
| IC shrinkage at 252 days | Keep, with the overlap fix in E13 |
| Calibration slope 0.5 to 1.5 | Keep, measured on the unshrunk forecast (E12) |
| Impact coefficient 0.5 | Keep as a floor (E17). Toth et al. (2011) put the peak-impact prefactor at "order unity". Average cost over a square-root path is about two thirds of peak, so 0.5 on cost implies a peak prefactor near 0.75. That two-thirds step is my own derivation and is unsourced |
| Volatility target 12% | Keep as an upper bound (E16) |
| Universe $5 and $10M | Keep, with hysteresis. Many catalyst-stage biotech names fall below these levels (Q5) |
| 30 claims for practitioners | Keep as a minimum. At 30 binary claims a 50% baseline is only excluded by a hit rate near 68% |
| Hard risk limits | Not changed |

**D11. SQLite with two writing processes.** The risk service is a separate process from the start, and both it and the main process write the audit log. SQLite in WAL mode handles this at low volume with one writer at a time. **Change:** none now. The audit log uses immediate transactions so concurrent appends cannot fork the hash chain.

---

## 4. Open questions for Aditi

Each has a recommended answer. v3.1 uses the recommendation until told otherwise. The same list is in `QUESTIONS.md`.

- **Q1. Buy survivorship-free data?** Recommended: Sharadar Bundle Full History at $499 per year, after reading its terms. Until then every real signal stays SURVIVORSHIP-BIASED at Tier 1 and the build uses fixtures.
- **Q2. Pay for Alpaca SIP data ($99 per month)?** Recommended: no for now. Build and test on IEX and fixtures, and accept that the staleness and spread limits will block many names.
- **Q3. JKP data is licensed non-commercial.** Is personal paper trading non-commercial for this purpose, and does that change if real money ever follows? Recommended: use it for research now and re-check before Phase 7.
- **Q4. Execution timing.** Recommended: sliced orders from 09:35 to 10:30 ET. The opening auction would need an exception to two safety invariants, and I did not make one.
- **Q5. Biotech names under $5 or $10M.** Recommended: keep the universe filter for the tradable book and allow a research-only biotech universe with its own lower filters.
- **Q6. What counts as failing monitoring?** Recommended: demote one tier when the trailing 252-day net return is below the 5th percentile of its expected distribution, or the data feed is unhealthy for 5 trading days.
- **Q7. How is a "correlated cluster" defined for the 20% hard limit?** Recommended: hierarchical clusters on 252-day residual return correlation, cut at 0.5, recomputed monthly. The limit value is unchanged.
- **Q8. Shadow period length for Tier 5.** Recommended: 63 trading days.
- **Q9. May the Composite be backfilled by walk-forward to build its IC history?** Without this, calibration needs more than a year of live running before any paper order. Recommended: yes, with only point-in-time inputs and weights, and the backfill labeled as such.
- **Q10. Sector scheme.** Recommended: SEC SIC codes mapped to Fama-French 12 industries, because GICS needs a licence.
- **Q11. The existing open decisions** (hard limit values, news provider, hosting, AI budget, non-US market order, tax review) are unchanged and still open.

---

## 5. Follow-up pass and what is still unverified

A second research pass covered the items the first pass did not reach.

**O17. Meta Content Library. CHANGED.** Independent review moved from ICPSR at the University of Michigan to CASD, the French Secure Data Access Center, announced 2025-12-08. Eligibility is still academic or not-for-profit research institutions. The spec's isr.umich.edu link is outdated. Source: https://transparency.meta.com/researchtools/secure-access-data-center/ **Change:** text and links updated.

**O18. FRED API. CHANGED in part.** A v2 API exists with one bulk endpoint. v1 is still documented, needs an API key, and serves ALFRED vintages through `realtime_start` and `realtime_end`. The official docs state neither a price for the key nor a rate limit. Source: https://fred.stlouisfed.org/docs/api/fred/ **Change:** source table names the v1 endpoint.

**O19. FINRA BrokerCheck. QUALIFIED.** No public API was found. FINRA's permitted-uses page allows compiling data for investor protection, academic, compliance or regulatory purposes. Use as an input to a trading system is outside that list. SEC adviser bulk files and the litigation release RSS feed are available. Source: https://www.finra.org/investors/learn-to-invest/choosing-investment-professional/about-brokercheck/permitted-uses **Change:** BrokerCheck lookups are manual and started by Aditi.

**Verified in the follow-up, no change needed.**
- YouTube captions.download "requires the user to have permission to edit the video". VERIFIED.
- ClinicalTrials.gov API v2 is current and the classic API retired in June 2024. SNIPPET.
- BLS v2 with a key: 500 queries per day, 50 series per query. BEA: key required, 100 requests per minute. VERIFIED.
- Crossref pools: public 5, polite 10, paid 150 requests (the unit is believed to be per second). arXiv: one request per 3 seconds. NBER RSS still offered. VERIFIED.
- Gu, Kelly and Xiu, RFS 33(5), 2223 to 2273. VERIFIED.
- statsmodels has `fdr_by` and HAC covariance. arch has the stationary and circular block bootstraps. VERIFIED.
- EDGAR XBRL facts carry a `filed` date, data starts in 2009, and the submissions JSON has `sic`. VERIFIED.

**Still unverified.**

- SSRN: no official API or feed was found and its terms page blocked fetches. Treat automated collection as not permitted until the terms are read.
- Whether a FRED API key is free and what the rate limit is. The official docs do not say.
- Benjamini-Yekutieli under arbitrary dependence, from a primary source. It is the textbook property and the spec relies on it.
- Impact prefactor values in Almgren et al. (2005) and Frazzini, Israel and Moskowitz.
- EDGAR coverage of deregistered companies.
- The licence on the Fama-French industry definitions. The files are free to download and carry a copyright notice with no licence text.
- Sharadar start year and licence text. Norgate licence text. Whether Alpaca serves bars for delisted symbols.
- Interactive Brokers figures, which were read from search snippets only.
- The seven data vendors listed under D3 as not reached.
