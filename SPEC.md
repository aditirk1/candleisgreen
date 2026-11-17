# CandleIsGreen Build Spec v3.1

Nov 17, 2026, @Aditi. v3.1 applies the technical fixes from `REVIEW.md`. Items that need Aditi's decision are in `QUESTIONS.md` and use the recommended default until answered. Hard risk limits are unchanged from v3. The change log is at the end.

## How to use this spec

This is the target architecture for CandleIsGreen and the order to build it in. Build Phase 0 and Phase 1 completely before touching later phases. A working paper-trading slice beats fifteen empty tabs.

Rules for the coding model:

1. Inspect the repository and environment first. Then build in small, tested steps.
2. Every default number in this spec (thresholds, limits, windows) lives in a versioned config file, not in code. Aditi can change them without a code edit.
3. Never fake a capability. A feature without data shows NOT AVAILABLE and the reason.
4. Never say "implemented" unless the code exists and its test or screen actually ran.
5. Every 45 to 60 minutes of work, commit to Git and update `HANDOFF.md` with the working state, exact commands, known flaws and the next atomic task.
6. When this spec is silent, pick the simplest option that passes the phase's acceptance test, and log the choice in `DECISIONS.md`.
7. No special code path for any named person, fund or paper. Everything enters through the same pipelines.

### First task: a review pass before any code

Before Phase 0, review this spec critically and write the result to `REVIEW.md`:

1. Check that every API, dataset, library and price named here is current, and note anything that changed.
2. Check every formula and default for errors and internal contradictions.
3. Look for better survivorship-free US data options and their costs.
4. List each disagreement with reasoning and a proposed change. Do not change hard risk limits.
5. The review ran on 2026-11-17 and its result is in `REVIEW.md`. Its technical fixes are applied in this v3.1. Decisions that belong to Aditi are in `QUESTIONS.md`, each with a recommended default that the build uses until she answers.

These defaults are judgment calls, not sourced values, and deserve the closest review: Composite eligibility at 80% probability, cold-start family spread of 5%, publication-bias factor of 0.74 outside US equities, the ω uncertainty factor of 0.5, signal and family caps of 20% and 35%, the 25% monthly weight-change limit, IC shrinkage at 252 days, the calibration slope band of 0.5 to 1.5, impact coefficient 0.5, the 12% volatility target, universe filters of $5 and $10M, the 30-claim bar for practitioners, and every hard risk limit.

Required repository files: `SPEC.md`, `REVIEW.md`, `QUESTIONS.md`, `README.md`, `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `SOURCE_REGISTRY.md`, `MODEL_REGISTRY.md`, `RESEARCH_PROTOCOL.md`, `RISK_POLICY.md`, `DESIGN_SYSTEM.md`, `DECISIONS.md`, `TEST_RESULTS.md`, `HANDOFF.md`.

## Product thesis and principles

CandleIsGreen is an evidence-driven quantitative research workstation that happens to trade, not a trading bot that happens to read research. Its central product is **the Composite**: one aggregate model built only from patterns that have been tested mathematically, replicated by others or by the platform, and confirmed out of sample net of costs. Papers, practitioners, filings and news feed the Composite. Risk controls and execution sit downstream of it and cannot be changed by it.

### Principles

1. **Three separate questions.** Does the effect exist (scientific validity)? Does it forecast better than a baseline out of sample (predictive accuracy)? Does it make money after costs at a realistic size (economic value)? Every signal shows all three, and passing one never implies the others.
2. **Evidence over fame.** Sources are judged by evidence for a specific claim in a specific domain. Follower counts, engagement and reputation carry no weight.
3. **Code computes, LLMs read.** Prices, features, forecasts, sizes and risk checks come from deterministic, versioned code. LLMs extract, summarize, explain and draft experiments. They never set a size, approve an order or override a risk check.
4. **Nothing trades because it was read.** A new paper or post creates an experiment, never an order.
5. **Everything has an as-of time.** Every observation, forecast, model version, approval and fill records when it became known and where it came from.
6. **Risk fails closed.** Risk runs as a separate process. Stale data, unknown instruments or ambiguous rules block the order. New strategies or data can never loosen a risk limit.
7. **Negative results are kept.** Failed replications and dead strategies stay visible so the system never rediscovers or cherry-picks them.
8. **Unknowns are shown.** No invented confidence, consensus estimate, track record or data freshness.
9. **Paper first.** Internal simulation and broker paper trading are the first deliverables. Real money is a separate, later project with live trading disabled by default.
10. **Runs without a paid LLM.** AI analysis is optional, cached and budget-capped. The default budget is zero.
11. **No subscriptions.** The platform uses only free data, free tools and free accounts. An option that needs a subscription or a monthly fee is not considered, recommended or built (Aditi, 2026-11-17). Each purpose uses a genuinely free dataset built for it, not a restricted free tier of a paid product. Unofficial scraping is never a primary dependency. A feature that has no adequate free data stays in the architecture and shows NOT AVAILABLE with the reason, read from `config/capabilities.yaml`.

## Architecture at a glance

The service diagram, interfaces and config layout are in `ARCHITECTURE.md`.

Data moves through collection and the point-in-time store into research, where only validated signals reach the Composite. The risk service checks every proposed order before the paper broker sees it, and fills feed back into signal monitoring. Approvals and the kill switch go from the workstation to the risk service only.

## Evidence tiers and the three scores

Every signal, whether it came from a paper, a practitioner or the platform's own search, carries one evidence tier. Only Tier 4 and above can enter the Composite, and only Tier 5 and above can receive paper capital.

| Tier | Name | Meaning | What it unlocks |
| --- | --- | --- | --- |
| 0 | Observation | Raw data: prices, filings, macro releases, fills | Feeds everything |
| 1 | Claim | An idea with no reproduction yet: a preprint, a practitioner post, a pattern the platform's own search found | Hypothesis Factory queue |
| 2 | Reproduced | The platform matched the original result on the original definitions and period | Independent testing |
| 3 | Independently replicated | Holds on a different period, universe, dataset or implementation, with the independence recorded | Out-of-sample economic test |
| 4 | Out-of-sample net | Beats its baseline out of sample, after modeled costs, under the validation protocol. The out-of-sample record may come from free portfolio returns built from a survivorship-free database (the years after the selection cutoff) or from the platform's forward record. A cross-sectional signal must pass twice: as a long-short portfolio (validity) and as its long-only implementation, the top portfolio against the market (economic value) | Composite at shadow weight |
| 5 | Shadow-confirmed | At least 63 trading days of pre-registered live forecasts on the platform's own stock-level forward record, issued before outcomes. Realized returns sit inside the pre-registered 90% band and the stock-level version tracks its Tier 4 portfolio-level record within the config limit. This is an implementation check. The evidence of edge is the Tier 4 test | Paper capital in the Composite |
| 6 | Paper-deployed | Trading in the paper account under governance | Eligible for a future live review |

**Evidence of edge and evidence of implementation are separate.** Edge can be judged now from decades of free portfolio returns: Open Source Asset Pricing and the Kenneth French library are built from CRSP, which includes delisted stocks, and every year after a factor's selection cutoff is out of sample. Implementation needs the platform's own stock-level data, which starts the day the forward recorder starts. So research and Tiers 2 to 4 can run from the first day, and the first paper capital needs only the 63-day Tier 5 shadow on the forward record. Portfolio returns cover the whole CRSP universe, including small names the platform will not trade, so their costs are modeled conservatively and the Tier 5 tracking check confirms the tradable version behaves the same.

Two routes reach Tier 3. A published signal gets there through replication by others or by the platform. A **new pattern** the platform discovers itself has no outside replication, so it must clear a stricter multiple-testing bar (see default decision criteria) and pass on a holdout period never touched during its search.

Demotion is automatic: a signal that fails monitoring drops one tier. A signal fails monitoring when its trailing 252-day net return is below the 5th percentile of its expected distribution, or its data feed is unhealthy for 5 trading days in a row. Promotion above Tier 4 needs Aditi's approval.

### The three scores, shown on every signal

| Score | Question | Measured by |
| --- | --- | --- |
| Validity | Does the effect exist? | Reproduction and replication results, effect size and interval, multiple-testing adjusted significance |
| Predictive accuracy | Does it forecast better than a baseline? | Out-of-sample loss against the baseline, rank correlation, calibration for probability forecasts |
| Economic value | Does it make money after costs at a realistic size? | Net return interval after doubled costs, turnover, capacity, drawdown |

## The Composite

The Composite is the single model CandleIsGreen trades. Each trading day it takes every eligible signal, estimates how much real edge each one has after accounting for publication bias and luck, weights them so correlated signals share a budget, combines them into one expected return per stock, and solves for target positions under the risk limits. This section defines it fully. Every number in it is a config default.

### C.1 Definitions

| Term | Definition |
| --- | --- |
| Universe U\_t | US common stocks and ETFs on day t with price at least $5 and 20-day median dollar volume at least $10M, using point-in-time membership including later-delisted names. A member leaves only when price falls below $4 or median dollar volume below $7.5M, so names near the line do not flip daily. Leveraged and inverse ETFs are excluded. Security type comes from a licensed source. Until one exists it is inferred from SEC form types and name rules and labeled `type_inferred` |
| Decision time | 16:30 ET each trading day. Only data with `first_usable_at` before 16:30 ET is used. Orders go out in the next regular session, sliced by the platform between 09:35 and 10:30 ET, and every slice passes the risk checks with a live quote. The opening auction is not used, because an auction order is sent while the market is closed and the safety invariants block that. A pre-open check at 09:00 ET cancels any buy in a name with an earnings release, halt or 8-K since decision time. It can cancel orders and can never add them |
| Signal s | A versioned, deterministic function that outputs a raw score x(s,i,t) for each asset i on day t. It declares a horizon h\_s in trading days, a type (cross-sectional or time-series), a family k, and an evidence tier |
| Family k | Group of related signals. Equity factors use the 13 JKP themes. Sectors, where needed, use SEC SIC codes mapped to the Fama-French 12 industries, because GICS needs a licence. Other families: trend, reversal, earnings events, corporate actions, macro, volatility, stat arb, news, biotech events, and one family per practitioner domain |
| Selection cutoff | The last date used to design or choose the signal. Paper signals: the latest of the paper's sample end, its first public date, and the date of the platform's last design choice for the signal (horizon, sector neutrality, smoothing). Platform discoveries: the start of the untouched holdout. Only returns after this date count as out-of-sample |

### C.2 Step 1: standardize every signal

1. **Cross-sectional signals.** Each day, winsorize raw scores at the 1st and 99th percentile across the universe, then convert to z-scores (subtract the cross-sectional mean, divide by the cross-sectional standard deviation). A signal may declare `sector_neutral: true`, in which case the z-score is computed within each sector.
2. **Time-series signals.** Divide each asset's raw score by its own rolling 252-day standard deviation, then clip to the range −3 to +3.
3. **Event signals** (earnings, FDA dates, index changes) are zero outside their event window.
4. **Smoothing to horizon.** Use an exponential moving average of the z-score with half-life h\_s / 2, so a 60-day signal does not churn daily. This is the only smoothing step. Cross-sectional scores are standardized again after smoothing. Event signals and practitioner claims skip the average and are forced to zero outside their window.
5. **Missing values** are set to 0, meaning no view.

Output: z(s,i,t) for every signal, asset and day.

### C.3 Step 2: build each signal's return series

Every signal gets a daily net return series so all signals can be compared on one scale.

- Research portfolio: weights proportional to the smoothed z-scores. Cross-sectional signals are dollar-neutral long-short. Time-series signals are directional per asset.
- The portfolio rebalances daily to the smoothed z-scores. There are no staggered cohorts, because the smoothing in C.2 already spreads a signal over its horizon and a second layer would double the holding period.
- The portfolio is scaled to 10% annualized ex-ante volatility using the Composite's risk model.
- Costs from the cost model below are subtracted at the portfolio's actual turnover.
- **Cost model.** Per trade: half the quoted spread, plus impact κ × σ\_daily × sqrt(trade dollars / ADV dollars) at a research NAV of $1M, plus regulatory fees on sells (SEC Section 31 and FINRA TAF rates from config). Short legs of research portfolios pay a borrow rate from config. Paper and simulated fills have no impact in them, so this model is applied on top of them in every P&L view.
- A cross-sectional signal also gets a long-only series: the top tercile by z-score against the universe return, net of costs. The Tier 4 economic test uses both series.

Result: daily net returns r(s,t). Summary statistics use only dates after the selection cutoff:

- r̄\_s = annualized mean out-of-sample net return
- σ\_s = its standard error, using Newey-West with lag min(h\_s, 63, T/4), where T is the number of out-of-sample days
- v\_s = the realized variance of the daily returns, annualized

These are long-short research portfolios. The executable book is long-only, and that constraint is applied in the optimizer, not here.

### C.4 Step 3: estimate each signal's true edge

Up to three independent pieces of evidence are combined by precision weighting. A piece that does not exist for a signal is left out.

| Evidence | Value | Variance |
| --- | --- | --- |
| Family prior | m\_k | τ\_k² |
| Paper measurement | δ\_k × R\_paper − C\_s, where R\_paper is the paper's reported in-sample return rescaled to 10% volatility and C\_s is the platform's modeled annual cost for the signal at 10% volatility. Papers report gross returns and the out-of-sample record is net, so the cost is taken off to compare like with like | (δ\_k × SE\_paper)² + ω², with ω = 0.5 × δ\_k × R\_paper and SE\_paper rescaled the same way as R\_paper |
| Out-of-sample record | r̄\_s | σ\_s² |

```latex
\hat{\mu}_s = \frac{\sum_j \theta_j / v_j}{\sum_j 1 / v_j}, \qquad V_s = \frac{1}{\sum_j 1 / v_j}, \qquad P_s = \Phi\!\left(\frac{\hat{\mu}_s}{\sqrt{V_s}}\right)
```

Here θ\_j and v\_j are the values and variances in the table, μ̂\_s is the estimated edge, V\_s its variance, and P\_s the probability the edge is positive.

A known property: with the paper measurement alone, μ̂/√V equals t / sqrt(1 + 0.25 t²), where t is the paper's t-statistic. δ\_k cancels, any paper with t above 0.93 gives P\_s of 0.80 or more, and P\_s cannot exceed 0.977. So for published signals P\_s is a weak filter, and the Tier 4 out-of-sample test is the binding one.

**Publication-bias factor δ\_k.** Defaults come from McLean and Pontiff, who found returns 26% lower out-of-sample and 58% lower after publication:

| Signal group | Default δ\_k | Reason |
| --- | --- | --- |
| US cross-sectional equity, published | 0.42 | Full post-publication decline |
| Non-US cross-sectional equity, published | 0.74 | Data-mining share only, since the post-publication decline was not reliable outside the US |
| Other published families | 0.74 | Same reasoning, wide uncertainty through ω |
| Platform discoveries and practitioners | Not used | No paper measurement. Only the family prior and out-of-sample record count |

Other estimates are less severe: Jensen, Kelly and Pedersen find post-sample alpha at about 0.53 of in-sample, and Chen and Zimmermann put pure publication bias near 0.88. The defaults keep the conservative end.

Once a family has 20 signals with both in-sample and out-of-sample records, δ\_k is replaced by the median ratio of out-of-sample to in-sample return in that family.

**Family prior m\_k and τ\_k.** The prior for signal s is computed from the other signals in its family, leaving s out, so its own record is not counted twice. With 5 or more other signals in a family: m\_k is the precision-weighted mean of their r̄\_s, and τ\_k² is the variance of their r̄\_s minus the average σ\_s² (floored at 1%²). With fewer than 5: m\_k = 0 and τ\_k = 5% per year at 10% volatility, which says "expect no edge, allow a Sharpe up to about 1 either way."

### C.5 Step 4: decide which signals are eligible

A signal enters the Composite only if all of these hold:

- Evidence tier 4 or higher. Tier 4 itself needs the lower bound of the 90% interval of net return above zero at doubled costs, so this is the stricter of the two statistical gates
- μ̂\_s above 0 and P\_s at least 0.80
- At least 252 trading days after its selection cutoff, or at least 30 independent events for event signals
- Its data feed is healthy today

Tier 4 signals get **shadow weight**: their weight is computed and tracked, but set to zero in the capital book. Tier 5 and above get capital weight.

### C.6 Step 5: weight the signals

1. **Within each family:** weights solve min w'Σ\_k w − 2 w'μ̂ subject to w ≥ 0, then are rescaled to sum to 1. Σ\_k is the Ledoit-Wolf shrunk covariance of the family's signal returns over the last 756 days (minimum 252). Without the sign constraint this is w = Σ\_k⁻¹ μ̂. With one or two signals, use w proportional to μ̂\_s / v\_s instead, where v\_s is the return variance from C.3. Signals whose return correlation is above 0.95 are merged into one signal first.
2. **Family returns:** each family's daily return is the weighted sum of its signals' returns.
3. **Across families:** hierarchical risk parity on the family return series. With fewer than 3 families, use inverse-variance weights.
4. **Final weight** w\_s = family weight × within-family weight.
5. **Caps:** no signal above 20% and no family above 35% of total weight. Excess is redistributed proportionally to uncapped signals, repeated until no cap binds or no uncapped signal is left. Weights may sum to less than 1. With fewer than 5 signals or fewer than 3 families the caps cannot fill the budget, and the remainder is recorded as `unallocated_weight`.
6. **Change limit:** no w\_s moves by more than the larger of 25% of its prior value and 2 percentage points in one monthly reweight without Aditi's approval. A new signal enters at 5% or less. Removal after a demotion or feed failure is immediate and exempt, and the freed weight stays unallocated until the next monthly reweight.

Reweighting runs on the first trading day of each month, and immediately when a signal is demoted or its feed fails.

### C.7 Step 6: combine into one score and an expected return per stock

1. Composite score: S(i,t) = sum over eligible signals of w\_s × g\_s × z(s,i,t), then demeaned and re-standardized across the universe to unit standard deviation. g\_s is the scale that brings signal s to 10% volatility in C.3, normalized to average 1, so the mix of signals in the book matches the mix the weights were fitted on. The market-direction content of time-series signals is removed by the demeaning and logged as a diagnostic. It is not traded in v3.1.
2. Expected return uses the standard information-coefficient rule:

```latex
\alpha_{i,t} = \mathrm{IC} \times \sigma_{i,t} \times S_{i,t}
```

Here σ\_i is the stock's forecast residual volatility over 21 days, and IC is the rolling out-of-sample rank correlation between S and next-21-day residual returns, shrunk toward zero as IC\_used = IC\_mean × n / (n + 252), with n the number of out-of-sample days. IC statistics use Newey-West errors with lag 21, because daily observations of 21-day returns overlap. α is clipped at three times IC × σ and scaled by the allocated share of weight, 1 − `unallocated_weight`.

3. **Calibration check (monthly):** regress realized 21-day residual returns on the unshrunk forecast IC\_mean × σ × S out of sample. The shrunk α is not used here, because the shrinkage alone would put the slope at (n + 252) / n, which is above 1.5 until day 504. The Composite is `calibrated` if the slope is between 0.5 and 1.5 and IC\_mean is positive with t above 2. If not, it shows ranks only (`signal_strength`) and the optimizer runs in reduce-only mode: it opens and adds to no position and may only cut.
4. **History for the check.** The Composite's own record is built by walk-forward backfill using only point-in-time inputs and weights, labeled as backfill, so the check does not need a year of live running.

### C.8 Step 7: solve for target positions

```latex
\max_{x}\; \alpha^{\top}x \;-\; \lambda\, x^{\top}\Sigma x \;-\; \sum_i \Big( c_i\,|x_i - x_{0,i}| + \kappa\,\sigma_i \sqrt{\tfrac{\mathrm{NAV}}{\mathrm{ADV}_i}}\; |x_i - x_{0,i}|^{3/2} \Big)
```

| Item | Definition and default |
| --- | --- |
| x, x₀ | Target and current weights as fractions of equity |
| Σ | Statistical factor model on 252 days of returns: Σ = B F B' + D. B holds loadings on 15 principal components, F is the Ledoit-Wolf shrunk covariance of the factor returns, and D holds specific variances shrunk halfway to their cross-sectional median. Names with under 126 days of history get average loadings and the median specific variance. Scaled to a 21-day horizon |
| Units | α and Σ are 21-day quantities. The impact term uses daily σ\_i and dollar ADV\_i. Costs are charged in full against the 21-day α, with a config field for the amortization horizon |
| c\_i | Half the quoted bid-ask spread |
| κ | Impact coefficient, default 0.5. Paper and simulated fills contain no market impact, so recalibration from them may raise κ and may never lower it below the default |
| λ | Chosen by bisection so the portfolio's ex-ante volatility is at most the target, default 12% annualized. When even the smallest λ gives less than the target, that portfolio is accepted with status `vol_below_target` |
| Constraints | Long-only, no leverage (weights sum to 1 or less), every hard limit in the risk table, sector weight at most 25% |
| No-trade band | Trades under 0.25% of equity are skipped |
| Solver | cvxpy with Clarabel. The 3/2 term uses `power(x, 1.5)` with `approx=False`, which gives the exact power cone |

The optimizer's output goes to the risk service, which checks it independently before any order.

### C.9 Practitioner and event signals

- A practitioner domain becomes a signal only after the person has 30 or more scored, falsifiable claims in it and beats a naive baseline with a stated interval. Each live claim sets z = +1 or −1 (times a stated confidence, if given) on the named asset, decaying linearly to 0 over the claim's horizon. Several people in one domain form one family.
- Event signals (earnings drift, FDA outcomes) produce a z-score only inside their event window and are otherwise identical.

### C.10 Output contract

Each daily run writes: `composite_run_id`, `as_of`, `universe_hash`, the list of signals used with tier, μ̂\_s, P\_s and w\_s, the `unallocated_weight`, per-asset S and α, calibration status, optimizer status, target weights, ex-ante volatility, and for each position the contribution of each signal to its α. The Reasoning screen reads this record directly.

### C.11 Worked example

A momentum signal. Its paper reports 8% per year at 10% volatility in-sample, standard error 2%. It is US cross-sectional, so δ = 0.42. The platform's modeled cost for it is 1.0% per year. Its out-of-sample record is 5.0% per year net with standard error 2.5%, which is t = 2.0 and a 90% lower bound of 0.9%, so it holds Tier 4. Its family has fewer than 5 signals, so the prior is 0 with τ = 5%.

| Evidence | Value | Variance | Precision |
| --- | --- | --- | --- |
| Paper | 0.42 × 8 − 1.0 = 2.36% | (0.42 × 2)² + 1.68² = 3.53 | 0.283 |
| Out-of-sample | 5.00% | 2.5² = 6.25 | 0.160 |
| Family prior | 0% | 5² = 25 | 0.040 |

Estimated edge: 3.04% per year, standard deviation 1.44%, probability positive 0.98. The signal is eligible.

A pure-noise signal with no paper and an out-of-sample record of 0.5% (standard error 2.5%) gets an estimated edge of 0.40% with probability positive 0.57. It is excluded on P\_s, and with t = 0.2 it would not reach Tier 4 either.

### C.12 Required tests

- Synthetic signals with known true edges: estimates recover them within their stated intervals at the stated rate.
- Pure-noise signals are excluded in at least 95% of simulated runs by the joint gate a signal actually faces: Tier 3 replication on independent data, the Tier 4 economic test after its cutoff, and P\_s. P\_s alone lets through up to 20% of zero-edge signals with long records. The Tier 4 test alone lets through about 5%, which is exactly the 95% bar with no margin, so neither is tested alone against it.
- Two identical copies of a signal together receive the same total weight as one copy, within 2 percentage points, measured before caps.
- With three signals the caps leave `unallocated_weight` of 40% and the weighting step ends.
- A score computed with any input whose `first_usable_at` is after decision time fails the build.
- A failed calibration check blocks new positions.
- The optimizer never returns a portfolio that breaks a hard limit, and the risk service rejects one that is injected deliberately.
- Frozen-weight and champion-challenger benchmarks run every day alongside the live Composite.

## Research pipeline and Hypothesis Factory

Every new paper, practitioner claim or self-discovered pattern becomes a pre-registered experiment with its decision rule fixed before any test runs. Negative results are stored as carefully as positive ones.

### Daily Hypothesis Factory loop

1. **Collect** new papers, code releases, filings, macro releases, news and captured commentary.
2. **Cluster** duplicates, reposts, paper versions and contradicting studies.
3. **Check novelty** against the existing signal library, the 13 JKP themes and stored definitions. A near-duplicate of an existing signal is linked to it, not tested as new.
4. **Write the claim card** (schema in the source registry section): definition, outcome, universe, horizon, mechanism, data needed, reported effect and costs, with page references for every extracted number.
5. **Check data.** If required data is missing, mark NEEDS\_DATA with the missing dataset, vendor and cheapest acceptable substitute.
6. **Pre-register** the test plan: null hypothesis, metric, benchmark, test windows, study type and its decision rule.
7. **Run in a sandbox.** Code from papers or the web is reviewed and sandboxed, never executed directly.
8. **Record the result** in the experiment registry, including every variant tried, which feeds the trial count.
9. **Publish a daily research digest**: new hypotheses, reproductions, failures, contradictions, drift alerts and data gaps.

Statuses: `DISCOVERED`, `EXTRACTED`, `NEEDS_DATA`, `REPRODUCING`, `REPRODUCED`, `FAILED`, `REPLICATED`, `OOS_PASSED`, `SHADOW`, `ELIGIBLE_FOR_REVIEW`, `PAPER`, `SUSPENDED`, `RETIRED`.

### Default decision criteria by study type

There is no single universal threshold. The t above 3.0 hurdle from [Harvey, Liu and Zhu](https://nber.org/papers/w20592) was built for newly discovered cross-sectional factors under heavy multiple testing, so it applies to that case only. All values below are config defaults.

| Study type | Default pass rule |
| --- | --- |
| Reproduction of a published result | Same sign, and effect inside the paper's reported interval or at least half its size |
| Independent replication | Same sign and significant at 5% on the new data, with the independence type recorded (period, universe, dataset, code) |
| New cross-sectional factor found by the platform's own search | t above 3.0, and false discovery rate under 5% across the full trial registry (Benjamini-Yekutieli), and a pass on an untouched holdout period |
| Event study (earnings, FDA, index changes) | Abnormal return interval excludes zero with clustered or HAC errors, false discovery control across events tested |
| Forecasting model | Beats its baseline out of sample at one-sided 5% and holds in at least two of three subperiods. Use Clark-West when the baseline is nested in the model, and Diebold-Mariano with the Harvey-Leybourne-Newbold correction otherwise |
| Economic test, any type | Lower bound of the block-bootstrap 90% interval of net excess return above zero at double modeled costs |

### Replication and contradiction tracking

The evidence graph records whether a replication is truly independent. Same-author code reuse, overlapping datasets and citation alone do not count. When a later study confirms or contradicts an active signal, the system opens a re-evaluation case, re-runs the signal's tests on current data, and updates its Composite prior. It never edits a live weight directly from a paper.

External implementations are versioned. [Open Source Asset Pricing](https://www.openassetpricing.com/) shipped its latest update on October 28, 2026, and its history includes a fix for a lookahead bug in one signal (AnnouncementReturn, release v1.4.1). The platform pins the version it tested and re-tests when the upstream code changes.

## Source registry and expert discovery

People and institutions are discovered by subject and judged by measured evidence, through one registry with no exceptions. There is no popularity score.

### Discovery

A weekly job runs a query library by subject across academic metadata (Crossref, OpenAlex, arXiv q-fin, NBER, SSRN), institution research pages, podcasts and permitted feeds. Subjects: factor investing, trend and carry, market microstructure, transaction costs, FX, rates, credit, global macro, options and volatility, dealer flows, earnings quality, accounting, valuation, asset pricing, ML methodology, reproducibility, biotech catalysts. New people enter as candidates until their identity is verified.

Seed candidates for discovery only, not endorsements and not followed for trades: Cliff Asness, Antti Ilmanen, Lasse Pedersen, Bryan Kelly, Dacheng Xiu, Andrew Chen, Tom Zimmermann, Campbell Harvey, Robert Carver, Corey Hoffstein, Euan Sinclair, Kris Abdelmessih, Benn Eifert, Brent Donnelly, Giuseppe Paleologo, Aswath Damodaran, Michael Mauboussin, Wesley Gray, Ernest Chan. Each is verified and scored like anyone else.

### Source profile

| Field | Values |
| --- | --- |
| `identity_status` | verified, unresolved, disputed |
| `domain_evidence` | Publications, verifiable roles with dates and sources, datasets, code |
| `claim_testability` | Share of claims with explicit target, direction and horizon |
| `track_record` | Per domain: scored claims, scoring rule, baseline, interval, sample size, or INSUFFICIENT DATA |
| `conflicts` | Disclosed commercial interests, paid products, documented regulatory records |
| `latency` | First-publication time and platform-ingestion time |
| `evidence_label` | direct data, reproducible paper, independently replicated, unreplicated, opinion, promotional |

### Identity and regulatory matching rule

A regulatory or enforcement record is attached to a person only when at least two strong identifiers match: CRD number, firm, or a filing that names both. A name and city match alone is stored as `possible_match_unresolved` and shown to Aditi for review, never applied automatically. Regulatory checks use FINRA BrokerCheck, the SEC adviser data files and the SEC litigation release feed. BrokerCheck has no public API and its permitted uses are investor protection, academic, compliance and regulatory purposes, so lookups there are manual and started by Aditi.

### Claim card schema

`claim_id`, `source_id`, `source_type`, `canonical_url`, `doi`, `title`, `author_ids`, `published_at`, `revised_at`, `ingested_at`, `first_actionable_at`, `market`, `instruments`, `target`, `horizon`, `direction`, `probability_if_stated`, `definition`, `mechanism`, `data_required`, `code_available`, `peer_review_status`, `replication_links`, `conflicts`, `license`, `test_plan_id`, `evidence_status`, `capture_hash`.

Commentary, forecasts, testable claims and portfolio disclosures are stored as different types. Only forecasts and testable claims are scored.

### Social platforms, realistically

- Broad Instagram search is not available to a personal app. Meta's Content Library offers full public-content search, but [applications are reviewed independently and access runs through a secure research environment](https://transparency.meta.com/researchtools/meta-content-library). Since December 2025 the reviewer is [CASD, the French Secure Data Access Center](https://transparency.meta.com/researchtools/secure-access-data-center/), which replaced ICPSR at the University of Michigan. Eligibility still depends on [affiliation with an academic or not-for-profit research institution](https://developers.facebook.com/docs/content-library-and-api/get-access). Treat it as a possible future academic route, not a dependency.
- YouTube's caption download endpoint [requires the user to have permission to edit the video](https://developers.google.com/youtube/data/reference/rest/v3/captions/download), so it cannot pull other creators' captions.
- Build a **Research Capture Inbox**: Aditi pastes a link, text or file. The system stores a hash and timestamp, extracts claims into claim cards, keeps summaries rather than full copied content, and shows a clear request for input whenever automatic retrieval is not allowed.
- Logged-in browser capture, where used, stays under Aditi's control and never exports passwords or cookies into the app.

## Data contract and point-in-time store

The backtester and every model read `first_usable_at`, the moment a value could actually have been acted on, never the date printed on a bar or filing. This one rule prevents most lookahead bias.

### Required fields on every observation and feature

`instrument_id`, `vendor`, `raw_symbol`, `exchange`, `field`, `value`, `event_time`, `published_at`, `vendor_available_at`, `ingested_at`, `first_usable_at`, `timezone`, `currency`, `adjustment_method`, `vintage`, `missing_flag`, `license`, `collection_mode`.

`first_usable_at` is derived, never typed in. For rows collected live it is the latest of `event_time`, `published_at`, `vendor_available_at` and `ingested_at`. For backfilled history (`collection_mode: backfill`) it is the latest of the first three plus a per-source lag from config, because the ingestion time of a backfill says nothing about when the value was known.

### Forecast contract (every model and the Composite)

`forecast_id`, `model_id`, `model_version`, `asset_id`, `issued_at`, `as_of`, `target_definition`, `target_start`, `target_end`, `expected_excess_return` or `signal_strength`, `quantiles` (if calibrated), `training_cutoff`, `data_snapshot_id`, `feature_snapshot_id`, `calibration_status`, `evidence_refs`, `eligible_for_orders`.

### Sources at launch

| Data | Source | Cost |
| --- | --- | --- |
| US prices and paper execution | Alpaca. [Paper trading is free](https://docs.alpaca.markets/docs/paper-trading). Only the free plan is used. Real-time quotes come from the IEX exchange only and feed the risk checks. Daily bars come from consolidated (SIP) history, which is free when the request ends at least 15 minutes in the past, so end-of-day data covers all exchanges. History starts in 2016. Paper fills ignore quote size and market impact | Free |
| US filings and fundamentals | SEC EDGAR submissions and XBRL APIs | Free |
| Equity factor library | Open Source Asset Pricing (US), JKP Global Factor Data (93 countries). Free downloads are factor and portfolio returns, plus signal documentation with each paper's sample period. Open Source Asset Pricing also publishes stock-level signals, but they are keyed to CRSP identifiers and a stock-level backtest with them needs CRSP returns, so they are not used at the stock level. JKP data is licensed for non-commercial use | Free for returns |
| Macro | FRED and ALFRED through the FRED API (v1 `series/observations` with `realtime_start` and `realtime_end` for vintages, API key required), BLS (500 queries per day with a key), BEA (100 requests per minute), central banks | Free |
| Papers | Crossref, OpenAlex (free key with a daily usage allowance), arXiv, NBER, SSRN where its terms allow | Free |
| Biotech events | ClinicalTrials.gov API, the FDA advisory committee calendar and FDA documents. FDA action dates come from company press releases and 8-K filings, since FDA publishes no calendar of them | Free |
| News | Lawful RSS feeds only | Free |
| Survivorship-free US history, forward | A Phase 1 collector records the full Alpaca asset list and daily bars for every listed US stock and ETF after each close. Every recorded day includes names that later delist, so the record is survivorship-free from its first day. For personal use only, never shared | Free |
| Survivorship-free US history, portfolio level | Open Source Asset Pricing portfolio returns and the Kenneth French data library, both built from CRSP, which includes delisted stocks. The Kenneth French files carry a copyright notice and no licence text, so they are used for personal research only | Free |
| Outside research tool, optional | QuantConnect's free cloud backtesting. It is not connected to the platform, and nothing from it enters the evidence pipeline. Its terms were not verified | Free |

### Capability map

`config/capabilities.yaml` lists every capability with status `available`, `limited` or `not_available`, its sources, and the reason for any gap. Code calls `require()` before using a capability, and an unavailable one raises. Screens show the label.

| Capability | Status | Reason |
| --- | --- | --- |
| US factor research | Available | Free portfolio returns built from CRSP |
| Global factor research | Limited | Returns only, non-commercial licence |
| US daily bars | Limited | From 2016, delisted coverage unconfirmed, labeled SURVIVORSHIP-BIASED |
| US stock history with delistings | Limited | Only from the day the forward recorder starts |
| Point-in-time fundamentals | Limited | SEC XBRL from 2009, using the filed date |
| Macro | Available | FRED, ALFRED, BLS, BEA |
| US paper execution | Available | Alpaca paper |
| Real-time consolidated quotes | Not available | The free real-time feed covers IEX only |
| Intraday trading | Not available | No free real-time consolidated data |
| Options data and options flow | Not available | No free source |
| Analyst consensus estimates | Not available | No free timestamped source, so earnings beat or miss is never shown |
| Licensed news | Not available | Lawful RSS only |
| Non-US execution | Not available | Non-US market data needs monthly fees |
| LLM features | Limited | Optional, off by default, local open-weight models only |

### Storage

- Analytical data: Parquet files queried with DuckDB.
- Transactional data (approvals, journal, registries, audit pointers): SQLite at first, Postgres when multiple processes write.
- Raw documents and captures: object storage with a content hash per item.
- Audit log: append-only and hash-chained so edits are detectable.

### Retention

| Data | Kept |
| --- | --- |
| Event metadata, structured news features, claim cards, experiments, decisions, orders, fills | Permanently |
| Licensed full-text news | The shorter of the license limit and 90 days |
| Captured social text | Summaries and hashes permanently, full text only where the terms allow |
| Daily and 1-minute bars | Permanently, where licensed |
| Tick data | 30 days, where licensed |

Views: NEWS LIVE (last 72 hours), RECENT (90 days, searchable), ARCHIVE (structured records, permanent).

### Mandatory survivorship rule

Historical tests use point-in-time universes that include delisted securities. When only a current-constituents list is available, the result is labeled SURVIVORSHIP-BIASED and cannot pass any gate. Two free sources meet the rule: the forward record from the Phase 1 recorder, from its first recorded day, and portfolio returns built from a database that includes delisted stocks.

## Model laboratory

Models are built in four levels, and each level must beat the one below it out of sample before it earns a place. Complexity is never assumed to help. That follows the comparative approach of Gu, Kelly and Xiu (2020), which tested ML methods against established asset-pricing benchmarks.

| Level | Models | Build when |
| --- | --- | --- |
| A. Transparent baselines | Buy and hold, time-series momentum, cross-sectional momentum, short-term reversal, moving-average and channel breakout, simple factor sorts, naive volatility, earnings surprise | First, in Phase 1 to 3 |
| B. Structured statistical | Regularized linear models, Bayesian dynamic linear models, Kalman filters, GARCH and HAR volatility, shrinkage covariance, cointegration and Ornstein-Uhlenbeck spreads, event-study regressions, hidden Markov regimes | After baselines are tested |
| C. Supervised ML | Elastic net, calibrated logistic regression, random forests, gradient-boosted trees, each compared against A and B | After B, with time-aware fitting and calibration |
| D. Experimental | Sequence models, transformers for event extraction, embeddings and topic models, deep probabilistic forecasting, reinforcement learning, meta-labeling, online model averaging | Research only until proven to add net value |

Every model registers its scope, data contract, horizon, refit schedule, version, output type, benchmark and out-of-sample record.

### Signal families

| Family | Examples | Horizon | Main failure modes |
| --- | --- | --- | --- |
| Trend and momentum | Volatility-scaled trend, return ranks, breakouts | Weeks to months | Whipsaw, crowding, costs |
| Reversal | 1 to 5 day reversal with liquidity filters | Days | Bid-ask bounce, illiquidity |
| Fundamental factors | JKP themes: value, quality, profitability, investment, low risk, accruals, issuance | Months | Accounting lookahead, delistings, capacity |
| Earnings events | Standardized unexpected earnings, drift, revisions, guidance | Days to months | Stale estimates, event timing |
| Corporate actions | Insider clusters, buybacks, spinoffs, index changes | Days to months | Announcement versus filing date |
| Macro and cross-asset | Rate and inflation surprises, curve, credit spreads, FX, commodities | Days to quarters | Data revisions, unstable correlations |
| Volatility | EWMA, GARCH, HAR, implied minus realized, skew, term structure | Days to weeks | Stale or sparse option data |
| Statistical arbitrage | Cointegrated pairs and baskets, sector-neutral spreads | Days to weeks | Breakdown of the relationship, borrow |
| News and text | Entity-event extraction, surprise versus expectation, novelty | Days. Minutes-scale use is NOT AVAILABLE | Duplicates, delayed feeds |
| Biotech catalysts | FDA action dates, trial phase, endpoints, effect sizes, cash runway | Event-dependent | Binary gaps, misread trial science |
| Practitioner claims | Scored claims from sources with enough history | Days to months | Selection bias, vague targets |
| Options and flow | Greeks, surface, put-call, dealer exposure scenarios. NOT AVAILABLE: no free options data. Kept in the architecture | Minutes to weeks | Dealer positioning is inferred, not observed |

Biotech catalysts are a natural edge given Aditi's background: each FDA date or readout is paired with trial design details (phase, endpoint, comparator, enrollment, prior data) and with how the market priced similar events before.

### Where LLMs are used

| Task | Tier |
| --- | --- |
| Claim cards, research digest, reasoning summaries | A locally hosted open-weight model, optional and off by default, cached. No paid API |
| News tagging, entity linking, translation, glossary lookups | Small model or rules |
| Anything that sets a number used in trading | Never an LLM |

## Validation protocol

Chronological out-of-sample testing is the backbone. Heavier tools are used where their assumptions hold, and every test reports the full number of variants tried, because trying many variants inflates the best result.

### Method by situation

| Situation | Method |
| --- | --- |
| Any time-series strategy | Walk-forward with a final holdout period never used for selection |
| Labels that overlap in time (multi-day horizons) | Purging and an embargo between train and test folds |
| Heavy model or parameter search | Combinatorial purged cross-validation and the [probability of backtest overfitting](https://papers.ssrn.com/abstract=2326253) |
| Reporting a Sharpe ratio after selection | [Deflated Sharpe ratio](https://papers.ssrn.com/abstract=2460551), only with the complete trial registry as input |
| Dependent returns | Block bootstrap intervals and HAC standard errors |
| Many hypotheses tested together | False discovery rate control across the experiment registry |

### Experiment manifest (required for every test)

- Question and null hypothesis
- Universe with point-in-time membership, region, period, counts
- Outcome, lookback, holding period, feature availability timestamps
- Train, validation and test scheme, embargo, every variant tried
- Independence of any replication and dataset overlap
- Fees, spread, slippage, impact, borrow, financing, FX, taxes, order timing
- Exposure, leverage, capacity
- Benchmarks: cash, buy and hold, a broad US equity ETF mixed with cash to the same volatility target as the book, a simple factor or ETF strategy, the current Composite
- What failed, and what could not be tested for lack of data

### Metrics by output type

| Output | Report |
| --- | --- |
| Portfolio | Gross and net return, CAGR, volatility, max drawdown, tail loss, turnover, exposure, benchmark-relative return, capacity |
| Forecast | Loss against baseline, out-of-sample R² where defined, rank correlation, calibration and Brier score for probabilities |
| Event signal | Abnormal return with interval, factor-adjusted alpha, multiple-comparison control |

Never optimize for win rate or raw Sharpe alone.

### Required failure fixtures

The test suite must include each of these and show the system catching it: lookahead from a revised filing, split or dividend error, ticker change, survivorship-biased universe, multiple testing without correction, duplicate news story, partial fill, broker timeout, stale quote, stop gapped through, halted market, daylight-saving boundary, missing FX rate, calibration collapse, missing consensus estimate, attempted live order, new paper contradicting an active signal.

## Risk, execution and governance

Risk is a separate service with its own permissions that checks every order and fails closed. The system may improve itself by proposing, testing and demoting, but it can never loosen a risk limit or promote a strategy to real money.

### Operating modes

| Mode | Orders | Default |
| --- | --- | --- |
| Research | None | On |
| Teaching and market watch | None | On |
| Manual simulation | Internal simulator after approval | On |
| Auto simulation | Internal simulator inside coded limits | On |
| Broker paper, approval | Paper account after each approval | After integration test passes |
| Broker paper, auto | Paper account under per-strategy permission | After integration test passes |
| Live, any form | Real money | **Not built in this project.** Every live route rejects orders even if real credentials are present |

PAPER or SIMULATION shows on every order view. Switching modes never silently changes accounts, credentials or permissions. The executable release trades long-only US stocks and ETFs. Shorts, leverage, options and futures get research and pricing screens only.

### Hard limits (Aditi sets the values, defaults shown)

| Limit | Default |
| --- | --- |
| Max position size | 5% of equity |
| Max per correlated cluster | 20% of equity |
| Max order size | 1% of 20-day average daily volume |
| Max bid-ask spread to trade | 0.5% |
| Daily loss stop | 2% of equity, halts new orders |
| Quote staleness | Over 15 seconds in market hours blocks the order |

A correlated cluster is a group from hierarchical clustering on 252-day residual return correlation, cut at 0.5 and recomputed monthly. This defines the term only. The limit value is Aditi's.

### Safety invariants

- Block the order when the quote is stale, account state is unknown, the instrument mapping is uncertain, the market is closed or halted, the broker is disconnected, or a rule cannot be evaluated.
- The kill switch and daily loss stop block new orders immediately. Flattening positions is a separate action that depends on liquidity and broker availability. Never promise it is instant.
- Stop orders do not cap losses. Prices can gap through them.
- Orders carry stable client IDs. After an uncertain broker response, query open orders before any retry. Never resubmit blind.
- Reconcile positions and fills with the broker after every order and at every session close.
- Every order shows its evidence-linked rationale and data freshness.

### Broker adapters

One adapter interface. Alpaca paper for US equities. There is no Interactive Brokers adapter, because its market data needs monthly fees (principle 11). Never claim an exchange or instrument is available without confirmed entitlements.

### Who can change what

| Change | Who | Guardrail |
| --- | --- | --- |
| Hard risk limits | Aditi only | Tightening applies now. Loosening waits 24 hours and asks again |
| Promote a signal to paper capital | System proposes, Aditi approves | Must hold Tier 5 with a complete experiment manifest |
| Composite weights | System, monthly | Max 25% change per weight per month without approval, frozen benchmark always running |
| Demote or suspend a signal | System, automatically | Logged with the evidence that triggered it |
| New experiments | System, automatically | Sandbox only, no capital |
| Model code changes | Aditi or the coding model, through Git | Full test suite must pass |

### Audit

Every signal, risk check, approval, order payload, broker response, status change, fill, cancellation and rule change records UTC event time, received time, strategy version and actor. The log is append-only and hash-chained. Rollback to any prior model or rule version takes one action.

## Teaching

Teaching runs alongside research and simulation on live markets. Every explanation cites an actual number and rule, the user predicts before the system reveals, and replay never shows information that was not yet known. Learning progress never unlocks real-money trading.

| Feature | Behavior |
| --- | --- |
| Live explanation stream | Short lines tied to real values: "14:05 ET. 20-day vol 24% annualized. Threshold 18%. Risk rule blocked the order." |
| Predict first | Before the reveal, the user states target, horizon and a probability. Scored with Brier or log score against a baseline |
| Calibration tracker | User's stated probabilities against outcomes, with sample size and interval, beside the Composite's |
| Decision reconstruction | Inputs, model versions, agreeing and opposing evidence, failed tests, risk check, data freshness |
| Why not? | For any ticker, why the system abstained or vetoed |
| Counterfactual | Change one input (remove a news item, widen the spread, raise vol), see whether the decision changes, labeled hypothetical |
| Replay | Any past session with as-known-then prices and news, including correction times. Missing intraday data is flagged, not invented |
| Crisis library | 1987, 1997, 2008, 2015 China, March 2020, 2022 rates. Each ends with what current rules would have done. An entry shows NOT AVAILABLE until licensed data covers its dates |
| Experiment lab | The user states a trade idea in plain words. The system turns it into a null hypothesis, data plan and out-of-sample test, and runs it through the same pipeline as any paper |
| Market autopsy | After each simulated trade: expected catalyst, what happened, spread paid, P&L attribution, which assumptions failed |
| Glossary | Locked, source-backed definitions with formulas and live values on hover |
| Concept map and daily lesson | Concepts linked by prerequisite, one lesson a day tied to a verified market event |
| Spaced review | Flashcards drawn from the user's own wrong predictions first |

Three explanation depths: Plain, Trader, Quant (formulas shown).

## Interface and design system

The interface ships with two themes over one layout and one component library, plus a Guide mode for learning. Aditi switches theme in Settings or with `THEME TERMINAL` and `THEME GLASS`. Build four working workflows before adding screens: Overview, Opportunities with Reasoning, Execution, and Research.

### Themes

Both themes are sets of CSS variables (design tokens). Components never hard-code colors or sizes, so a theme switch changes tokens only.

| Token | Terminal (dense, Bloomberg-style) | Glass (modern, calm, direct) |
| --- | --- | --- |
| Background | #0B0D10 | Dark: gradient #0E1420 to #16213A. Light option: #F3F5F9 |
| Panels | #12151A, 1 px #232830 border | Frosted: white at 6% opacity with 16 px background blur, 1 px white border at 12%. Light option: white at 70% |
| Text, muted text | #D7DCE2, #8A93A0 | #E8EDF5, #9AA6B8 (light: #111827, #4B5563) |
| Accent | Amber #FFB000 | Blue #5B8CFF |
| Gain, loss | #3FB950, #F85149 | #34C78A, #FF6B6B |
| Numbers | IBM Plex Mono or JetBrains Mono, tabular | Inter with tabular figures |
| Labels | IBM Plex Sans or Inter, 12 to 13 px | Inter, 14 px base |
| Rows | 28 px | 40 px |
| Corners | 2 px | 12 px |
| Default density | Many panes, every column | Fewer panes, key columns, more space |

Rules for both: never encode meaning by color alone (always a sign or arrow too), colorblind-safe gain and loss option, text contrast at least 4.5:1 (WCAG AA).

Rules for Glass so it stays readable:

- Blur and translucency go on navigation, headers and cards only. Tables, charts and numbers sit on panels at 85% opacity or more.
- When the system asks for reduced transparency, Glass panels turn solid.
- Motion is limited to fades under 150 ms. No parallax, glow or animated backgrounds.

### Guide mode

Guide mode is separate from theme, on by default with Glass, and available with either.

- **Plain labels.** Column names in everyday words with the technical term on hover: "Expected gain (alpha)", "How much it swings (volatility)", "Chance the edge is real (P)".
- **What does this mean?** Every metric has a hover card: one-line meaning, the formula, and a "typical range" line so a beginner can tell whether a number is high or low.
- **Simple Overview.** Three numbers first (account value, today's change, risk in use), everything else one click down.
- **Show pro columns.** Advanced columns stay hidden until toggled on, per screen.
- **Explain this screen.** A button that walks through the current screen using today's actual numbers.
- **First-run tour** of the four core screens.
- **Plain-language commands.** The command bar also accepts phrases like "show Nvidia news" or "why didn't we buy Apple" and maps them to the coded commands.

Guide mode never hides risk warnings, the PAPER label or the kill switch.

A persistent status strip shows mode (PAPER or SIMULATION), account, market session, feed latency, API status and the kill switch.

### Writing rules for every string

No em dashes, semicolons, middle-dot separators, tildes as separators, filler, metaphors, slogans or exclamation marks. Units go in column headers. Abbreviations come from the glossary. Times are 24-hour with zone (14:32 ET), dates ISO (2026-11-16). A trade rationale is at most six short lines, with full evidence one click away. Alerts are one line: ticker, event, number, time.

### Screens

| Screen | Focus |
| --- | --- |
| Overview | Equity curve, open risk, daily P&L, mode, feed health, alerts |
| Opportunities | Proposed positions, expected return assumptions, entry, validation status, risk result |
| Reasoning | For one candidate: evidence, agreeing and opposing signals, exclusions, uncertainty, risk check |
| Execution | Approval queue, orders, fills, reconciliation, kill switch |
| Research | Claim cards by status, experiments, evidence graph, failure archive |
| Composite | Signals in the Composite, tiers, the three scores, weights, champion versus challenger |
| Markets | Instrument search, watchlists, charts, sector and factor context |
| News | Clustered events showing what happened, why it may matter and what prices did, kept separate |
| Earnings | Calendar and scorecards. "Beat" or "miss" appears only when a timestamped consensus estimate exists |
| Experts | Source registry with provenance and measured claim records |
| Backtests | Walk-forward, holdout, cost stress, trial count beside every Sharpe |
| Learn | Teaching features |
| Global | Sessions, macro calendars, FX, data entitlement map |
| Audit and Rules | Versions, events, approvals, rollbacks |
| Settings | Providers, credential status, costs, permissions, accessibility |

Layout pattern: a sortable table on the left, an evidence pane on the right. Command bar examples: `NVDA NEWS`, `NVDA EARN`, `RESEARCH PEAD`, `COMPOSITE`, `BACKTEST MOMENTUM`, `RULES`, `KILL`.

## Global markets

Research covers the world from early on. Execution starts with US stocks and ETFs and expands market by market, each only after its data entitlements, rules and adapter are tested.

- **Research data.** JKP Global Factor Data covers 153 equity factors in 93 countries for free, so global factor research can start before any global execution.
- **Execution reach.** Interactive Brokers offers [over 170 market centers in 29 currencies](https://www.interactivebrokers.com.hk/en/general/about/ibkr-fact-sheet.php) from one account, but each market needs its own market data subscription. Under principle 11 there is no non-US execution. Every non-US instrument is `research_only`.
- **Instrument tags.** Every instrument is `direct` (tradable now), `proxy` (exposure through an ADR, ETF or future) or `research_only`. Unsupported markets cannot receive orders.
- **Market rule table.** One record per exchange: hours, auctions, price limits, short-sale rules, settlement, holidays, lot sizes, transaction taxes. Filled from official exchange documents and read by the risk service before every order.
- **Follow the sun.** Jobs run by session: Asia-Pacific, Europe, US, then overnight review. All times stored in UTC.
- **Currency.** P&L splits into local return and FX return. Hedging is a per-position decision made by the risk service.
- **Per-market evidence.** A signal's tier is tracked separately in each market. Post-publication decay differs by market, so a signal that faded in the US is tested on its own in other markets.
- **Access limits.** Some markets restrict foreign retail ownership (India and mainland China among them). Tag those `proxy` or `research_only` until the rules and broker support are confirmed.
- **Tax.** Track foreign withholding. Non-US funds can create PFIC reporting for US taxpayers, so foreign funds stay research-only until a tax professional has reviewed them.

## Technology stack

One stack, chosen now so the coding model does not build two.

| Layer | Choice | Reason |
| --- | --- | --- |
| Language | Python 3.14 for backend and research, 3.12 as the minimum | Quant library ecosystem. 3.12 and 3.13 are security-only as of Nov 2026 |
| API | FastAPI with Pydantic v2 schemas, exact version pinned | Typed contracts between services. FastAPI ships breaking 0.x releases often |
| Frontend | React with TypeScript on Vite, AG Grid Community for tables and TradingView Lightweight Charts | A dense multi-pane terminal with keyboard control needs a real frontend. Streamlit cannot meet the design bar |
| Analytical store | Parquet and DuckDB | Fast local point-in-time queries |
| Transactional store | SQLite, moving to Postgres when needed | Approvals, journal, registries |
| Scheduling | APScheduler 3.x, then a durable queue when volume requires | Simple first. APScheduler 4 is still alpha |
| Statistics and ML | numpy, pandas 3, statsmodels, scikit-learn, LightGBM, arch (GARCH), cvxpy with Clarabel | Standard, tested |
| Language models | Optional, a locally hosted open-weight model | Zero cost. Off by default |
| Brokers | `alpaca-py` for Alpaca paper. No other broker (principle 11) | `alpaca-trade-api` is archived |
| Testing | pytest, hypothesis for invariants, recorded API fixtures | Reproducible tests |
| Secrets | Environment variables or the OS credential store, never Git or logs | Safety |
| Hosting | Aditi's own computer for scheduled jobs and the interface. A job that missed its time catches up on the next run and marks what it collected late | No server rental under principle 11. Global research has no live deadlines, so it does not need an always-on machine |

The services:

1. **Collectors**: stateless jobs for prices, filings, research, news and captures, with checkpoints and a source health dashboard.
2. **Point-in-time store**: normalizes, deduplicates and records provenance and availability times.
3. **Research processor**: claim cards, evidence graph, Hypothesis Factory, experiment registry.
4. **Quant engine**: features, models, backtester, forecasts, the Composite, model registry.
5. **Risk and execution**: separate process and permissions, broker adapters, reconciliation, audit log.
6. **Workstation**: the interface and teaching.

Agent names in the interface are roles, not separate recurring LLM calls. Document costs in `README.md`. The target is zero, and any cost that appears is a bug in the plan.

## Build phases and acceptance tests

Eight phases. Each ships only when its acceptance test passes and `HANDOFF.md` records the result. Phase 0 and Phase 1 done well matter more than everything after them.

| Phase | Scope | Pass when |
| --- | --- | --- |
| 0. Repository and contracts | Directories (`sources/`, `data/`, `research/`, `models/`, `composite/`, `backtests/`, `risk/`, `broker/`, `ui/`, `tests/`), typed schemas, UTC rules, config file, audit log, fixtures, CI command | One offline event flows end to end with immutable IDs. A planted lookahead leak is caught |
| 1. US paper vertical slice | Daily data from fixtures or Alpaca, the forward recorder of the full US asset list and daily bars (started as early as possible, because every day it runs adds clean history), one Level A trend baseline, candidate trade, risk check, approval or auto-simulation, journal, minimal Overview and Execution screens | Approval, rejection, fill, stale-feed block and kill switch all verified end to end |
| 2. Broker paper and filings | Alpaca paper adapter, reconciliation, SEC filing timestamps and XBRL facts, earnings scorecard | A duplicate submission is not repeated. Every financial figure traces to an SEC filing. No "beat" without a consensus estimate |
| 3. Research engine and the first Composite | Claim cards, evidence graph, experiment registry, two published factor reproductions (one passing, one expected to fail), Composite v0 over three Level A signals with shrinkage and frozen-weight benchmark. Reproductions, replications and the Tier 4 out-of-sample test use free portfolio returns built from CRSP, so they can run as soon as this phase starts. Stock-level work runs on fixtures and synthetic data until the forward record exists, and results on older Alpaca history stay labeled SURVIVORSHIP-BIASED at Tier 1 | Full evidence chain shown in the UI. Negative result stored and visible. Composite output traces to each signal's weight and evidence |
| 4. News and teaching | Lawful RSS ingestion, event clustering, Reasoning screen, predict first, one full historical replay | Replay cannot see later news or prices at earlier timestamps |
| 5. Hypothesis Factory and model levels B and C | Daily research loop, decision criteria by study type, champion and challenger, calibration, drift monitoring, practitioner claim scoring | A model update never changes risk limits or permissions. A contradicting paper opens a re-evaluation case |
| 6. Global research | JKP global factor returns, instrument taxonomy, exchange calendars, market rule table, FX split. No non-US execution (principle 11) | Every non-US instrument is `research_only` and cannot receive orders. A week of global research jobs runs with no manual step |
| 7. Live trading (separate project) | Threat model, independent review, broker permissions, capped manual-approval prototype | Not started without a separate written decision from Aditi |

## Open decisions for Aditi

- [ ] Hard limit values in the risk table (defaults are placeholders)
- [x] Survivorship-free US data: free only. The forward recorder and free portfolio-level returns, as in `QUESTIONS.md` Q1. CRSP through a university WRDS account is for academic research only, so it is not used
- [x] News provider: lawful RSS only
- [x] Hosting: Aditi's own computer (`QUESTIONS.md` Q13)
- [x] AI budget: zero
- [x] Non-US markets: research only, no execution
- [ ] Tax professional review before any foreign fund or non-US holding

## Change log, v3 to v3.1

Each line cites the finding in `REVIEW.md`.

- Tiers: Tier 4 now tests the long-only implementation as well (D4). Tier 5 has a defined shadow period and band (E21). Monitoring failure is defined (E29).
- C.1: universe hysteresis, leveraged ETF exclusion, security type and sector sources (E26, E29). Regular-session slicing replaces the opening auction, with a pre-open cancel check (E24, E27). Selection cutoff includes the platform's design choices (D9).
- C.2 and C.3: one smoothing step, no staggered cohorts, event signals stay inside their window (E11). Cost model defined, with borrow and fees (E29, O12). Newey-West lag capped (E20).
- C.4: paper return net of modeled cost (E4). Leave-one-out family prior (E5). The δ cancellation is documented (E3).
- C.5 and C.12: the noise test is on the joint gate (E2). Duplicate-signal test has a tolerance (E19).
- C.6: constrained weights (D7), variance in the fallback (E6), w\_s notation (E7), feasible caps with `unallocated_weight` (E8), workable change limit (E9).
- C.7: volatility scale g\_s (E10), calibration on the unshrunk forecast and residual returns (E12, E14), overlap-aware IC statistics (E13), reduce-only mode (E29), walk-forward backfill (Q9).
- C.8: units (E15), factor model definition (E18), κ floor (E17), volatility as an upper bound (E16), solver settings (O10).
- C.11: the example signal now passes Tier 4 (E1).
- Decision criteria: "and" for new factors (E22). Clark-West for nested forecasts (D8).
- Sources: Meta Content Library reviewer, FRED API detail and BrokerCheck permitted uses updated (O17 to O19).
- Data: `first_usable_at` rule (E23). Source table corrected for Alpaca, the factor libraries, OpenAlex and FDA dates (O1 to O3, O7, O8, O11, O13).
- Stack: Python 3.14, APScheduler 3.x, Clarabel, current broker SDKs (O4, O6, O9, O10).
- Phase 3 runs on fixtures until data is licensed (E25).
- Hard risk limits: no change.

Amendment, 2026-11-17, from Aditi: no subscription-based platform and no monthly fee. Added principle 11. Removed the paid data, paid real-time feed, licensed news, server rental and Interactive Brokers execution. Added the forward recorder to Phase 1 and free portfolio-level history to Phase 3. Phase 6 is global research only.

Amendment 2, 2026-11-17, from Aditi: free datasets by purpose. Edge is judged on free portfolio returns from day one, and the forward stock record is needed only for the 63-day Tier 5 implementation check. Daily bars come from Alpaca's delayed consolidated history. Added the capability map. Options flow, intraday trading, real-time consolidated quotes and analyst estimates are NOT AVAILABLE and stay in the architecture. Language models are optional and local. QuantConnect is an optional outside tool, not connected.

## Sources

- [Harvey, Liu and Zhu, ...and the Cross-Section of Expected Returns](https://nber.org/papers/w20592)
- McLean and Pontiff (2016), Does Academic Research Destroy Stock Return Predictability?, Journal of Finance, https://doi.org/10.1111/jofi.12365
- Jensen, Kelly and Pedersen (2023), Is There a Replication Crisis in Finance?, Journal of Finance, https://doi.org/10.1111/jofi.13249
- Gu, Kelly and Xiu (2020), Empirical Asset Pricing via Machine Learning, Review of Financial Studies, https://doi.org/10.1093/rfs/hhaa009
- [Open Source Asset Pricing, release notes](https://www.openassetpricing.com/)
- [Bailey and López de Prado, The Deflated Sharpe Ratio](https://papers.ssrn.com/abstract=2460551)
- [Bailey, Borwein, López de Prado and Zhu, The Probability of Backtest Overfitting](https://papers.ssrn.com/abstract=2326253)
- [Meta Content Library and API, access and eligibility](https://transparency.meta.com/researchtools/meta-content-library)
- [YouTube Data API, captions download](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)
- [Alpaca Trading API and paper trading](https://docs.alpaca.markets/docs/trading-api)
- [Interactive Brokers fact sheet](https://www.interactivebrokers.com.hk/en/general/about/ibkr-fact-sheet.php)
- SEC EDGAR APIs, https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- FRED and ALFRED, https://fred.stlouisfed.org and https://alfred.stlouisfed.org
