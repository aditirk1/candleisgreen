# CandleIsGreen Build Spec v3.2

Nov 22, 2026, @Aditi. v3.2 consolidates Aditi's decisions on the review questions into the v3.1 spec. Each decision is in the decisions register near the end, with its assumptions, implementation, validation test and failure behavior. v3.1 applied the technical fixes from `REVIEW.md`. Hard risk limit values are unchanged from v3. The change log is at the end.

## How to use this spec

This is the target architecture for CandleIsGreen and the order to build it in. Build Phase 0 and Phase 1 completely before touching later phases. A working paper-trading slice beats fifteen empty tabs.

Rules for the coding model:

1. Inspect the repository and environment first. Then build in small, tested steps.
2. Every number in this spec lives in a versioned config file, not in code, and is classified in `config/parameters.yaml` by its evidentiary basis (see Parameter basis). Do not turn a provisional research threshold into a hard rule. Aditi can change values without a code edit, within the change policy of their basis.
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

These defaults are judgment calls, not sourced values, and deserve the closest review. Each is now classified in `config/parameters.yaml` as provisional or as a safeguard, never as empirical: Composite eligibility at 80% probability, cold-start family spread of 5%, publication-bias factor of 0.74 outside US equities, the ω uncertainty factor of 0.5, signal and family caps of 20% and 35%, the 25% monthly weight-change limit, IC shrinkage at 252 days, the calibration slope band of 0.5 to 1.5, impact coefficient 0.5, the 12% volatility target, universe filters of $5 and $10M, the 30-claim bar for practitioners, and every hard risk limit.

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
12. **Evidence, safeguards and settings are kept apart.** A number backed by published evidence, a number that limits damage and a number that is simply a starting point are labeled differently and changed under different rules (see Parameter basis).

## Parameter basis

Every value in `config/default.yaml` has one basis in `config/parameters.yaml`. A test fails if any value is unclassified. The basis decides how the software treats the value.

| Basis | What it is | Required record | How the software treats it | Who may change it |
| --- | --- | --- | --- | --- |
| Empirical | A value taken from published evidence, such as the publication-bias factor δ from McLean and Pontiff | Citation | Shown as EMPIRICAL with the source. May be replaced by platform evidence with provenance, as δ is once a family has 20 signals | Aditi, with a new cited source or platform evidence in the experiment registry |
| Safeguard | An engineering protection that limits damage: hard risk limits, concentration caps, the cost multiplier, limit-orders-only, the execution-grade feed list | Change policy | Enforced by the risk service or the optimizer. `assert_tunable` refuses any experiment, search or optimizer that tries to vary it | Aditi only. Loosening a hard limit waits `risk.loosening_delay_hours` and asks again |
| Provisional | An initial configuration with no evidence behind the exact number: P ≥ 0.80, 252 days, the universe filters, the execution window, the monitoring alert level | What evidence would change it | Shown as PROVISIONAL wherever it decides an outcome. A gate result names the config path of each provisional threshold that decided it. Experiments may vary it, and every variant counts in the trial registry | Aditi, or proposed by an experiment and approved |
| External fact | An official or conventional number that is not a threshold: a fee rate, the market time zone | Source and as-of date | Shown with its date. Updated when the source changes | Updated from the source |

A research threshold is a provisional default unless the registry marks it empirical. Passing or failing one is a statement about the current configuration, not a proof.

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
| 3 | Independently replicated | Holds on a different period, universe, dataset or implementation, with the independence recorded. Academic portfolio returns after the selection cutoff support the hypothesis at this tier | Building and testing an executable approximation |
| 4 | Executable approximation passes | A stock-level version the platform can actually trade is built and evaluated by the platform's own code on platform data, with realistic transaction costs, under the validation protocol. A cross-sectional signal must pass twice: as a long-short portfolio (validity) and as its long-only implementation (economic value). Academic portfolio evidence enters the edge estimate but cannot pass this tier on its own | Composite at shadow weight, and prospective shadow trading starts |
| 5 | Prospectively validated | Pre-registered prospective forecasts on the platform's survivorship-aware forward record, issued before outcomes, for at least 63 trading days and also meeting the strategy's trade-count and precision requirements. Realized returns sit inside the pre-registered band and the executable version tracks its research record within the config limit. Retrospective results never count here | Paper capital in the Composite |
| 6 | Paper-deployed | Trading in the paper account under governance | Eligible for a future live review |

**Academic evidence supports a hypothesis. It does not certify a tradable implementation.** Open Source Asset Pricing and Kenneth French portfolio returns are built from CRSP, which includes delisted stocks, and every year after a factor's selection cutoff is out of sample. So research, reproduction and replication can start on the first day. That evidence covers the whole CRSP universe, including small names the platform will not trade, with academic portfolio construction and no realistic costs. Promotion therefore also needs an executable approximation evaluated independently by the platform with realistic costs (Tier 4) and prospective validation on the platform's own forward record (Tier 5). Shadow trading starts as soon as the executable approximation is ready, so the first simulated trade does not wait for the observation period to end.

Two routes reach Tier 3. A published signal gets there through replication by others or by the platform. A **new pattern** the platform discovers itself has no outside replication, so it must clear a stricter multiple-testing bar (see default decision criteria) and pass on a holdout period never touched during its search.

Monitoring separates two kinds of failure. **Infrastructure failure** (missing critical data, invalid prices, a failed risk check) pauses the affected trading at once, with no statistics involved. **Strategy deterioration** is judged against the strategy's forecast distribution on rolling out-of-sample evidence, and that distribution includes both the uncertainty of the edge estimate and the sampling noise of the window, so a short window needs a larger shortfall before it alerts. A deterioration alert demotes the signal one tier and opens a re-evaluation case. The window and alert level are provisional, and a strategy may declare its own. There is no universal rule such as "252 days below the 5th percentile". Promotion above Tier 4 needs Aditi's approval.

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
| Universe U\_t | US common stocks and ETFs on day t with price at least $5 and 20-day median dollar volume at least $10M, computed only from information available at decision time, with survivorship-aware membership that keeps historical asset IDs, inactive and later-delisted names. The $5 and $10M filters are provisional. A member leaves only when price falls below $4 or median dollar volume below $7.5M, so names near the line do not flip daily. Spread, halt and liquidity checks apply at order time. Leveraged and inverse ETFs are excluded. A separate research-only biotech universe (`universe.research_universes.biotech`) has no price or volume filter and can never receive orders. Security type comes from a licensed source. Until one exists it is inferred from SEC form types and name rules and labeled `type_inferred` |
| Decision time | 16:30 ET each trading day. Only data with `first_usable_at` before 16:30 ET is used. Orders go out in the next regular session as paper limit orders, sliced by the platform inside a configurable window, initially 09:35 to 10:30 ET. Every slice passes the risk checks with a fresh execution-grade quote, a spread check and the participation limit. Delayed consolidated prices are used for research and end-of-day data, never to price an order. If no suitable fresh quote exists, the slice is rejected. Every fill records its slippage against the arrival mid, and alternative windows are compared on that record before a permanent default is chosen. The opening auction is not used, because an auction order is sent while the market is closed and the safety invariants block that. A pre-open check at 09:00 ET cancels any buy in a name with an earnings release, halt or 8-K since decision time. It can cancel orders and can never add them |
| Signal s | A versioned, deterministic function that outputs a raw score x(s,i,t) for each asset i on day t. It declares a horizon h\_s in trading days, a type (cross-sectional or time-series), a family k, and an evidence tier |
| Family k | Group of related signals. Equity factors use the 13 JKP themes. Sectors use SEC SIC codes mapped to the Fama-French 12 industries, with the classification date and mapping version stored. A missing or ambiguous classification is UNKNOWN, and all UNKNOWN names share one bucket under the same caps, so they cannot evade an exposure limit. Other families: trend, reversal, earnings events, corporate actions, macro, volatility, stat arb, news, biotech events, and one family per practitioner domain |
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

Up to four independent pieces of evidence are combined by precision weighting. A piece that does not exist for a signal is left out.

| Evidence | Value | Variance |
| --- | --- | --- |
| Family prior | m\_k | τ\_k² |
| Paper measurement | δ\_k × R\_paper − C\_s, where R\_paper is the paper's reported in-sample return rescaled to 10% volatility and C\_s is the platform's modeled annual cost for the signal at 10% volatility. Papers report gross returns and the out-of-sample record is net, so the cost is taken off to compare like with like | (δ\_k × SE\_paper)² + ω², with ω = 0.5 × δ\_k × R\_paper and SE\_paper rescaled the same way as R\_paper |
| Academic out-of-sample record | Mean academic portfolio return after the selection cutoff, at 10% volatility, minus modeled cost | SE² + (g × mean)², where g is the provisional `implementation_gap_factor` (default 0.5), because the academic portfolio is not the tradable version |
| Out-of-sample record of the executable approximation | r̄\_s | σ\_s² |

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
- μ̂\_s above 0 and P\_s at least 0.80 (provisional)
- At least 252 trading days of out-of-sample record for the executable approximation, or at least 30 independent events for event signals (both provisional)
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
4. **History for the check.** The Composite's history may be reconstructed by walk-forward, using only point-in-time inputs and weights chosen without future information. The development history and the parameter-selection process are stored with it. Every reconstructed forecast carries `record_type: retrospective`, is shown separately from recorded prospective forecasts, can never be eligible for orders, and never counts as the untouched prospective test that Tier 5 requires.

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

Each daily run writes: `composite_run_id`, `as_of`, `universe_hash`, the record type (prospective or retrospective), the data licenses behind it, the list of signals used with tier, μ̂\_s, P\_s and w\_s, the reasons and config paths for every exclusion, the `unallocated_weight`, per-asset S and α, calibration status, optimizer status, target weights, ex-ante volatility, and for each position the contribution of each signal to its α. The Reasoning screen reads this record directly.

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
- Academic portfolio evidence alone never yields capital weight.
- A strategy performing as forecast triggers deterioration alerts at about the stated rate, and a dead strategy triggers them more often as evidence accumulates.
- Promotion fails without 63 prospective days, the strategy's trade count, enough precision, a result inside the band, acceptable tracking, or with a retrospective record.

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

There is no single universal threshold. The t above 3.0 hurdle from [Harvey, Liu and Zhu](https://nber.org/papers/w20592) was built for newly discovered cross-sectional factors under heavy multiple testing, so it applies to that case only. All values below are provisional defaults in `config/parameters.yaml`, not universal statistical laws.

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

`license` is a license ID from `config/licenses.yaml`, and every derived result keeps the license IDs of the data behind it.

`first_usable_at` is derived, never typed in. For rows collected live it is the latest of `event_time`, `published_at`, `vendor_available_at` and `ingested_at`. For backfilled history (`collection_mode: backfill`) it is the latest of the first three plus a per-source lag from config, because the ingestion time of a backfill says nothing about when the value was known.

### Forecast contract (every model and the Composite)

`forecast_id`, `model_id`, `model_version`, `asset_id`, `issued_at`, `as_of`, `target_definition`, `target_start`, `target_end`, `expected_excess_return` or `signal_strength`, `quantiles` (if calibrated), `training_cutoff`, `data_snapshot_id`, `feature_snapshot_id`, `calibration_status`, `evidence_refs`, `eligible_for_orders`, `record_type` (`prospective` or `retrospective`), `data_licenses`.

A forecast issued after its target window started must be `retrospective`, and a retrospective forecast can never be eligible for orders. An order is built only when every license in `data_licenses` permits paper trading. `unverified` counts as not permitted.

### Instrument master and corporate actions

The forward record is survivorship-aware, not automatically survivorship-free: it is only as complete as what was collected. It keeps:

- a permanent `instrument_id` with its symbol, exchange and status history (`active`, `inactive`, `delisted`) and valid-from and valid-to dates
- corporate actions (splits, dividends, mergers, spin-offs, symbol changes, delistings) with their announcement and effective dates
- inactive and delisted securities, never deleted
- completeness flags per day and source: whether the asset-list snapshot was taken, when it was actually taken, which bars are missing, and whether a value was collected live or backfilled
- sector classifications with SIC code, Fama-French 12 industry, classification date, mapping version and `unknown` status

### Licenses

`config/licenses.yaml` records, for each license ID, whether research and paper trading are permitted. JKP data (CC BY-NC 4.0) is permitted for noncommercial academic and personal research. Its paper-trading use is `unverified` until the license interpretation is checked, so JKP-derived results stay research only. Kenneth French data and some FRED series are also `unverified` for trading use.

### Sources at launch

| Data | Source | Cost |
| --- | --- | --- |
| US prices and paper execution | Alpaca. [Paper trading is free](https://docs.alpaca.markets/docs/paper-trading). Only the free plan is used. Real-time quotes come from the IEX exchange only and feed the risk checks. Daily bars come from consolidated (SIP) history, which is free when the request ends at least 15 minutes in the past, so end-of-day data covers all exchanges. History starts in 2016. Paper fills ignore quote size and market impact | Free |
| US filings and fundamentals | SEC EDGAR submissions and XBRL APIs | Free |
| Equity factor library | Open Source Asset Pricing (US, CC BY 4.0), JKP Global Factor Data (93 countries, CC BY-NC 4.0, tagged and kept separate by license). Free downloads are factor and portfolio returns, plus signal documentation with each paper's sample period. Open Source Asset Pricing also publishes stock-level signals, but they are keyed to CRSP identifiers and a stock-level backtest with them needs CRSP returns, so they are not used at the stock level. JKP data is licensed for non-commercial use | Free for returns |
| Macro | FRED and ALFRED through the FRED API (v1 `series/observations` with `realtime_start` and `realtime_end` for vintages, API key required), BLS (500 queries per day with a key), BEA (100 requests per minute), central banks | Free |
| Papers | Crossref, OpenAlex (free key with a daily usage allowance), arXiv, NBER, SSRN where its terms allow | Free |
| Biotech events | ClinicalTrials.gov API, the FDA advisory committee calendar and FDA documents. FDA action dates come from company press releases and 8-K filings, since FDA publishes no calendar of them | Free |
| News | Lawful RSS feeds only | Free |
| Survivorship-aware US history, forward | A Phase 1 collector records the full Alpaca asset list, including inactive assets, daily consolidated bars and corporate actions for every US stock and ETF after each close, with completeness flags. It is survivorship-aware from its first day, and complete only where the flags say so. For personal use only, never shared | Free |
| Survivorship-free US history, portfolio level | Open Source Asset Pricing portfolio returns and the Kenneth French data library, both built from CRSP, which includes delisted stocks. The Kenneth French files carry a copyright notice and no licence text, so they are used for personal research only | Free |
| Outside research tool, optional | QuantConnect's free cloud environment, for Aditi's own exploration. It is not a dependency, nothing from it enters the evidence pipeline, and no market data is extracted from it into CandleIsGreen, because its published terms restrict exporting platform data | Free |

### Capability map

`config/capabilities.yaml` lists every capability with status `available`, `limited` or `not_available`, its sources, and the reason for any gap. Code calls `require()` before using a capability, and an unavailable one raises. Screens show the label.

| Capability | Status | Reason |
| --- | --- | --- |
| US factor research | Available | Free portfolio returns built from CRSP |
| Global factor research | Limited | Returns only, non-commercial licence |
| US daily bars | Limited | From 2016, delisted coverage unconfirmed, labeled SURVIVORSHIP-BIASED |
| US stock history with delistings | Limited | Survivorship-aware only from the day the forward recorder starts, and only as complete as its flags show |
| Point-in-time fundamentals | Limited | SEC XBRL from 2009, using the filed date |
| Macro | Available | FRED, ALFRED, BLS, BEA |
| US paper execution | Available | Alpaca paper |
| Real-time consolidated quotes | Not available | The free real-time feed covers IEX only |
| Intraday trading | Not available | No free real-time consolidated data |
| Options data and options flow | Not available | No free source |
| Analyst consensus estimates | Not available | No free timestamped source, so reported results are never compared with a consensus |
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
| Daily and 1-minute bars, the instrument master, corporate actions and completeness flags | Permanently, where licensed |
| Tick data | 30 days, where licensed |

Views: NEWS LIVE (last 72 hours), RECENT (90 days, searchable), ARCHIVE (structured records, permanent).

### Mandatory survivorship rule

Historical tests use point-in-time universes that include delisted securities. When only a current-constituents list is available, the result is labeled SURVIVORSHIP-BIASED. Free sources and what they can support:

- **Academic portfolio returns built from CRSP** include delisted stocks. They support hypotheses (Tiers 2 and 3) and enter the edge estimate, but never certify an implementation.
- **The forward record** is survivorship-aware from its first recorded day, as complete as its flags show. Tier 5 prospective validation runs on it.
- **Older Alpaca history** (from 2016) is labeled SURVIVORSHIP-BIASED. A biased result never passes a gate that grants capital. It may serve as the Tier 4 executable-approximation check, with its label shown, only alongside survivorship-free academic evidence for the same hypothesis, because Tier 4 grants shadow weight and no capital.

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
| Walk-forward reconstruction of past decisions | Point-in-time inputs and weights only, with the development history stored. Labeled RETROSPECTIVE and never pooled with prospective forecasts |

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

Exposure limits combine two classifications. **Fama-French 12 sectors** carry the provisional 25% sector cap. **Correlation clusters** (hierarchical clustering on 252-day residual return correlation, cut at 0.5, recomputed monthly) carry the 20% correlated-cluster limit, which stays configurable. A name counts in its sector and its cluster, each limit is checked separately, and neither can be used to bypass the other. Exposure includes current positions and pending orders. Names with a missing or ambiguous classification share one UNKNOWN bucket under the same limits. Cluster stability is tested monthly by comparing consecutive assignments, and an unstable clustering falls back to sector limits plus an alert. The limit value is Aditi's.

### Safety invariants

- Block the order when the quote is stale, account state is unknown, the instrument mapping is uncertain, the market is closed or halted, the broker is disconnected, or a rule cannot be evaluated.
- The kill switch and daily loss stop block new orders immediately. Flattening positions is a separate action that depends on liquidity and broker availability. Never promise it is instant.
- Stop orders do not cap losses. Prices can gap through them.
- Orders carry stable client IDs. After an uncertain broker response, query open orders before any retry. Never resubmit blind.
- Reconcile positions and fills with the broker after every order and at every session close.
- Every order shows its evidence-linked rationale and data freshness.
- Orders are limit orders only. The limit may not sit further from mid than the spread limit allows.
- Only execution-grade quote feeds (`risk.hard_limits.execution_grade_feeds`) can price an order. Delayed consolidated data is never on that list.
- An order outside the configured execution window is blocked.
- Missing critical data, invalid prices or a failed risk check pause the affected trading at once.
- A target book is checked independently for positions, clusters, sectors and the UNKNOWN bucket before any order is built from it.

### Broker adapters

One adapter interface. Alpaca paper for US equities. There is no Interactive Brokers adapter, because its market data needs monthly fees (principle 11). Never claim an exchange or instrument is available without confirmed entitlements.

### Who can change what

| Change | Who | Guardrail |
| --- | --- | --- |
| Hard risk limits and other safeguards | Aditi only | Tightening applies now. Loosening a hard limit waits 24 hours and asks again. No experiment or optimizer may vary a safeguard |
| Empirical parameters | Aditi | Needs a new cited source or platform evidence in the experiment registry |
| Provisional parameters | Aditi, or proposed by an experiment | Every variant tried counts in the trial registry. Changes are logged with the evidence |
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

- **Parameter basis tags.** A number or decision that depends on a provisional parameter shows a PROVISIONAL tag. Hover shows the registry entry: basis, source or review note, and who may change it. Empirical values show their citation.
- **Record type tags.** Retrospective results show RETROSPECTIVE and are never charted on the same line as prospective forecasts.

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
| Language | Python 3.13 for development and deployment, compatible with 3.12 where feasible. 3.14 is added only after a full dependency and test-suite check | 3.13 runs the full test suite today |
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
| Hosting | Oracle Cloud Always Free for scheduled jobs, with local execution and a local scheduled task as the fallback. The interface runs locally. The account is never upgraded | Zero cost. Oracle documents idle reclamation, capacity shortages and fixed home regions, so every job is safe to rerun and catches up after a gap (see decision Q13) |

The services:

1. **Collectors**: stateless jobs for prices, filings, research, news and captures, with checkpoints and a source health dashboard.
2. **Point-in-time store**: normalizes, deduplicates and records provenance and availability times.
3. **Research processor**: claim cards, evidence graph, Hypothesis Factory, experiment registry.
4. **Quant engine**: features, models, backtester, forecasts, the Composite, model registry.
5. **Risk and execution**: separate process and permissions, broker adapters, reconciliation, audit log.
6. **Workstation**: the interface and teaching.

Module boundaries are typed and tested: research, models and the Composite never import the broker or the pipeline, the risk engine imports only shared contracts, and the data layer never imports research, risk or brokers.

Agent names in the interface are roles, not separate recurring LLM calls. Document costs in `README.md`. The target is zero, and any cost that appears is a bug in the plan.

## Build phases and acceptance tests

Eight phases. Each ships only when its acceptance test passes and `HANDOFF.md` records the result. Phase 0 and Phase 1 done well matter more than everything after them.

| Phase | Scope | Pass when |
| --- | --- | --- |
| 0. Repository and contracts | Directories (`sources/`, `data/`, `research/`, `models/`, `composite/`, `backtests/`, `risk/`, `broker/`, `ui/`, `tests/`), typed schemas, UTC rules, config file, audit log, fixtures, CI command | One offline event flows end to end with immutable IDs. A planted lookahead leak is caught |
| 1. US paper vertical slice | Daily data from fixtures or Alpaca, the survivorship-aware forward recorder of the full US asset list with inactive assets, daily bars, corporate actions and completeness flags (started as early as possible, because every day it runs adds history), one Level A trend baseline, candidate trade, risk check, approval or auto-simulation, journal, minimal Overview and Execution screens | Approval, rejection, fill, stale-feed block and kill switch all verified end to end |
| 2. Broker paper and filings | Alpaca paper adapter with limit orders, reconciliation, slippage measurement against the arrival mid and a comparison of alternative execution windows, SEC filing timestamps and XBRL facts, SIC classifications with dates and mapping versions, earnings scorecard | A duplicate submission is not repeated. Every financial figure traces to an SEC filing. No "beat" without a consensus estimate |
| 3. Research engine and the first Composite | Claim cards, evidence graph, experiment registry, two published factor reproductions (one passing, one expected to fail), Composite v0 over three Level A signals with shrinkage and frozen-weight benchmark. Reproductions and replications use free portfolio returns built from CRSP, so they can run as soon as this phase starts. Executable approximations are tested on platform data with realistic costs, and prospective shadow trading starts as soon as one is ready. Results on older Alpaca history keep their SURVIVORSHIP-BIASED label | Full evidence chain shown in the UI. Negative result stored and visible. Composite output traces to each signal's weight and evidence |
| 4. News and teaching | Lawful RSS ingestion, event clustering, Reasoning screen, predict first, one full historical replay | Replay cannot see later news or prices at earlier timestamps |
| 5. Hypothesis Factory and model levels B and C | Daily research loop, decision criteria by study type, champion and challenger, calibration, drift monitoring, practitioner claim scoring | A model update never changes risk limits or permissions. A contradicting paper opens a re-evaluation case |
| 6. Global research | JKP global factor returns, instrument taxonomy, exchange calendars, market rule table, FX split. No non-US execution (principle 11) | Every non-US instrument is `research_only` and cannot receive orders. A week of global research jobs runs with no manual step |
| 7. Live trading (separate project) | Threat model, independent review, broker permissions, capped manual-approval prototype | Not started without a separate written decision from Aditi |

## Decisions register (v3.2)

Aditi's decisions of 2026-11-22 on the review questions. Each lists its assumptions, implementation, validation test and failure behavior. "Built" means code and a passing test exist. "Planned" names the phase. The zero-subscription constraint (principle 11) holds for all of them.

### Q1. Data for research and implementation

| Item | Content |
| --- | --- |
| Decision | Three free sources: academic portfolio returns (Open Source Asset Pricing, Kenneth French), the platform's forward-collected universe, and older Alpaca history. The forward universe is survivorship-aware, not automatically survivorship-free. Academic portfolio evidence never substitutes for stock-level implementation tests |
| Assumptions | Alpaca's free plan lists inactive assets and serves daily consolidated bars once 15 minutes have passed. Whether it serves bars for delisted symbols is unconfirmed and is checked when the recorder is built |
| Implementation | Planned, Phase 1: the recorder stores the instrument master with status history, corporate actions, inactive and delisted securities and per-day completeness flags (see Instrument master). Built: the observation contract with `collection_mode`, the capability map entry, and the rule that academic evidence alone never grants capital |
| Validation test | Built: `test_academic_evidence_cannot_grant_capital_without_prospective_tier`. Planned: a delisted name stays in the instrument master with its delisting date, a missed day sets a completeness flag, and a ticker change keeps one `instrument_id` |
| Failure behavior | A day with no asset-list snapshot is flagged incomplete, never silently filled. A test on data with incomplete delisting coverage carries the SURVIVORSHIP-BIASED label |

### Q3. JKP license

| Item | Content |
| --- | --- |
| Decision | JKP data is used for noncommercial academic and personal research. The dataset and everything derived from it stay tagged by license. Paper or real-money use is not assumed authorized until the license interpretation is checked |
| Assumptions | JKP data is CC BY-NC 4.0 (verified on jkpfactors.com, 2026-11-17) |
| Implementation | Built: `config/licenses.yaml` marks `cc_by_nc_4_0` paper trading as `unverified`. Observations carry a license ID, forecasts carry `data_licenses`, and the pipeline refuses to build an order unless every license permits paper trading |
| Validation test | Built: `test_noncommercial_data_is_research_only_until_checked`, `test_a_jkp_derived_forecast_cannot_become_an_order` |
| Failure behavior | An unknown, missing or unverified license blocks the order and names the license |

### Q4. Execution timing and quality

| Item | Content |
| --- | --- |
| Decision | Next-session execution by default, inside a configurable window, initially 09:35 to 10:30 ET. Paper limit orders, quote-quality checks, spread limits and participation limits. Execution is rejected when suitable fresh data is unavailable. Delayed consolidated prices are never execution-grade. Slippage is measured and alternative windows compared before a permanent default is chosen |
| Assumptions | The free real-time IEX feed is the only execution-grade quote available at zero cost. Paper fills contain no market impact, so window comparisons on paper fills measure spread and quote quality, not impact |
| Implementation | Built: the window, feed, quote-size and limit-price checks in `risk/engine.py`, limit-order-only intents, a simulator that fills only marketable limits, and `slippage_bps` on every fill. Planned, Phase 2: the window comparison report |
| Validation test | Built: tests for an order outside the window, a delayed consolidated quote, a quote with no size, a limit too far from mid, a resting non-marketable limit, and slippage against arrival mid |
| Failure behavior | Any missing, stale, delayed or zero-size quote blocks the slice. A non-marketable limit rests unfilled and is never chased with a market order |

### Q5. Universe

| Item | Content |
| --- | --- |
| Decision | Provisional tradable filters of $5 minimum price and $10M median daily dollar volume, computed from information available at decision time, plus spread, halt and liquidity checks. A separate research-only biotech universe without these filters |
| Assumptions | SIC codes 2834, 2835, 2836 and 8731 cover biotech closely enough for research. This list is provisional |
| Implementation | Built: the filter values and the research universe in config, classified as provisional, and the spread, halt and participation checks in the risk engine. Planned, Phase 1: the universe builder |
| Validation test | Built: the risk tests for spread, halts and participation. Planned: the universe on day t uses no data with `first_usable_at` on or after decision time, and a research-universe name can never produce an order intent |
| Failure behavior | A name with an unknown price or volume at decision time is left out of the tradable universe. A research-universe order is refused |

### Q6. Monitoring

| Item | Content |
| --- | --- |
| Decision | Infrastructure failure and strategy deterioration are separate. Missing critical data, invalid prices or failed risk checks pause affected trading at once. Strategy performance is monitored against its forecast distribution on rolling out-of-sample evidence that accounts for sample uncertainty. The 252-day 5th-percentile rule is not a universal test |
| Assumptions | Returns over the window are approximately normal after Newey-West correction, and the edge estimate's variance V\_s is a fair measure of its uncertainty |
| Implementation | Built: `composite/monitoring.py` with `infrastructure_check` and `deterioration_test`, which compares the realized mean with a predictive distribution of variance V\_s plus the window's sampling variance. Window and alert level are provisional and per-strategy |
| Validation test | Built: a strategy performing as forecast alerts at about the stated rate, a dead strategy alerts more as evidence grows, short records are not judged, and edge uncertainty widens the distribution |
| Failure behavior | Infrastructure failure pauses trading in the affected names at once. A deterioration alert demotes one tier and opens a re-evaluation case. Below the minimum observation count the status is `insufficient_data`, not a pass |

### Q7. Exposure limits

| Item | Content |
| --- | --- |
| Decision | Fama-French sector limits plus correlation-based clusters. The 20% cluster cap stays configurable. Cluster stability is tested, exposure includes current positions and pending orders, and overlapping classifications cannot bypass aggregate limits |
| Assumptions | Monthly clustering on 252 days of residual returns is stable enough to be useful. If not, sector limits carry the load |
| Implementation | Built: pending orders in the position and cluster checks, separate sector and cluster checks in `evaluate_portfolio`, an UNKNOWN bucket in the optimizer and the book check. Built: the monthly clustering job (`clusters.py`) on residual returns with its stability test and sector fallback |
| Validation test | Built: tests for pending buys pushing a position or cluster over its limit, sector and cluster counted separately, and unknown sectors pooled. Built: `tests/test_clusters.py` recovers planted groups, keeps market-only correlation from forming one cluster, falls back to sectors when stability drops below `clustering.min_stability`, and blocks a name a stable clustering does not cover |
| Failure behavior | Unknown pending orders or cluster membership block the order. An unstable clustering falls back to sector limits and raises an alert |

### Q8. Shadow period and promotion

| Item | Content |
| --- | --- |
| Decision | A 63-trading-day minimum shadow period, plus trade-count and precision requirements appropriate to each strategy. Shadow trading starts when the implementation is ready, and the first simulated trade does not wait for the period to end |
| Assumptions | 63 trading days is a floor, not a sufficient sample. Low-turnover strategies need more time to reach their trade count |
| Implementation | Built: `promotion_check` in `composite/eligibility.py` with a per-strategy `StrategyPromotionPolicy`. The 63-day minimum cannot be lowered by a strategy |
| Validation test | Built: promotion fails without 63 days, the trade count, enough precision, a result in band, acceptable tracking, or with a retrospective record. A strategy may declare its own trade count but not fewer days |
| Failure behavior | A strategy that does not meet its requirements stays at Tier 4 in shadow. It is never promoted on time served alone |

### Q9. Walk-forward reconstruction

| Item | Content |
| --- | --- |
| Decision | Historical walk-forward reconstruction of the Composite is allowed with point-in-time inputs and weights chosen without future information. The development history and parameter-selection process are stored. Retrospective results are labeled separately and never treated as equivalent to an untouched prospective test |
| Assumptions | Point-in-time inputs remove data lookahead but not researcher lookahead, because the method was designed after seeing history |
| Implementation | Built: `record_type` on every forecast. A forecast issued after its target window started must be retrospective, and a retrospective forecast can never be eligible for orders. Planned, Phase 3: the experiment registry stores the development history and every parameter variant tried |
| Validation test | Built: `test_late_forecast_cannot_be_labeled_prospective`, `test_retrospective_forecast_can_never_trade`, and promotion refusing a retrospective record |
| Failure behavior | A mislabeled forecast fails validation and is not stored |

### Q10. Sector classification

| Item | Content |
| --- | --- |
| Decision | SEC SIC codes mapped to Fama-French 12 industries, with classification dates and mapping versions. Missing or ambiguous classifications are UNKNOWN and cannot evade exposure limits |
| Assumptions | The Fama-French 12 SIC mapping from the Kenneth French library is usable for personal research. Its license text was not found |
| Implementation | Built: the UNKNOWN bucket in the optimizer and the book check. Planned, Phase 2: classification records from EDGAR with SIC code, industry, date and mapping version |
| Validation test | Built: `test_unknown_sectors_share_one_capped_bucket`, `test_optimizer_caps_the_unknown_bucket` and the sector book check |
| Failure behavior | An unmapped SIC code becomes UNKNOWN and is capped with the other unknowns |

### Q11. Python version

| Item | Content |
| --- | --- |
| Decision | Develop and deploy on Python 3.13. Keep 3.12 compatibility where feasible. Add 3.14 only after a full dependency and test-suite check |
| Assumptions | Every pinned library publishes 3.13 wheels, which held when the suite ran |
| Implementation | Built: `.python-version` is 3.13 and `requires-python` is 3.12 or later |
| Validation test | Built: the full suite on 3.13. Planned: a 3.12 run when an interpreter is available |
| Failure behavior | A library without 3.13 wheels is not adopted |

### Q12. Package layout

| Item | Content |
| --- | --- |
| Decision | The `candleisgreen` package layout is accepted, with clear module boundaries and typed interfaces between research, execution, risk, data and the UI |
| Assumptions | None beyond the layout in `ARCHITECTURE.md` |
| Implementation | Built: the package, Pydantic contracts and a boundary test that parses every import |
| Validation test | Built: `test_module_boundaries_hold` |
| Failure behavior | A forbidden import fails the build |

### Q13. Hosting

| Item | Content |
| --- | --- |
| Decision | Prefer Oracle Cloud Always Free, with local execution and a local scheduled task as the fallback when free cloud capacity is unavailable |
| Assumptions | Checked on Oracle's pages, 2026-11-22. Always Free is zero cost while the account is never upgraded, and upgrading cannot be undone. Signup needs a credit card. Oracle may reclaim an Always Free instance idle for 7 days (95th-percentile CPU, network and, on Ampere, memory all under 20%), and a daily job would likely look idle. Accounts idle for 30 days may be suspended. Free capacity in the home region can run out for days, and the home region cannot be changed |
| Implementation | Planned, Phase 1: every job is safe to rerun and catches up after a gap, writes a heartbeat after each run, and copies recorded data back to Aditi's computer after each run. The local scheduled task runs the same command when the heartbeat is missing. No artificial load is generated to avoid the idle rule. The account is never upgraded |
| Validation test | Planned: running a job twice gives the same stored result, a missing heartbeat triggers the local run, and a skipped day is caught up and flagged |
| Failure behavior | If the instance is reclaimed or capacity is unavailable, the local fallback runs. If both miss a day, daily bars are backfilled later as `backfill` and the missing asset-list snapshot stays flagged |

### Q14. Academic evidence and promotion

| Item | Content |
| --- | --- |
| Decision | Portfolio-level academic evidence supports a research hypothesis. It does not certify the tradable implementation. Promotion needs an independently evaluated executable approximation, realistic transaction costs and prospective validation |
| Assumptions | Academic portfolios use the full CRSP universe and academic weighting, so their returns overstate what the tradable version earns |
| Implementation | Built: academic evidence enters C.4 with the extra variance (g × mean)², capital needs Tier 5, and Tier 5 needs a prospective record. Tiers 4 and 5 are redefined above |
| Validation test | Built: `test_academic_evidence_supports_but_never_dominates`, `test_academic_evidence_cannot_grant_capital_without_prospective_tier` |
| Failure behavior | A signal with academic support and no executable approximation stays at Tier 3 |

### Q15. QuantConnect

| Item | Content |
| --- | --- |
| Decision | QuantConnect is optional, for outside exploration only. It is never a dependency, and no proprietary market data is extracted from it into CandleIsGreen |
| Assumptions | QuantConnect's published terms restrict exporting platform data. Aditi stated this, and it was not re-verified here |
| Implementation | Nothing to build. No code path reads from QuantConnect |
| Validation test | Not applicable |
| Failure behavior | Not applicable |

## Open decisions for Aditi

- [ ] Hard limit values in the risk table (defaults are placeholders)
- [ ] Tax professional review before any foreign fund or non-US holding
- [x] Every review question Q1 to Q15, decided 2026-11-22 (decisions register above)

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

Version 3.2, 2026-11-22, from Aditi's decisions on the review questions:

- Parameter basis: every config value is classified as empirical, safeguard, provisional or external fact, and research thresholds are provisional defaults, not hard rules (new section and principle 12).
- Tiers: Tier 4 is the independently evaluated executable approximation with realistic costs, and Tier 5 is prospective validation with per-strategy trade-count and precision requirements (Q8, Q14). Academic evidence supports hypotheses and enters C.4 with an implementation gap (Q14).
- Monitoring: infrastructure failure and strategy deterioration are separate, and deterioration is judged against the forecast distribution (Q6).
- C.1: survivorship-aware universe from decision-time information, research-only biotech universe (Q1, Q5). Limit orders, execution-grade quotes, configurable window and slippage measurement (Q4). Classification dates, mapping versions and the UNKNOWN bucket (Q10).
- C.7 and the forecast contract: retrospective and prospective records kept apart (Q9). License tags on data and derived results (Q3).
- Data: instrument master, corporate actions and completeness flags (Q1). License registry (Q3).
- Risk: sector and cluster limits checked separately, pending orders counted, unknowns pooled (Q7).
- Stack: Python 3.13 (Q11). Oracle Cloud Always Free with local fallback (Q13). Module boundaries tested (Q12). QuantConnect outside only (Q15).
- Hard risk limit values: no change. The execution-grade feed list was added as a safeguard.

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
- Jacobs and Müller (2020), Anomalies across the globe: Once public, no longer existent?, Journal of Financial Economics, https://doi.org/10.1016/j.jfineco.2019.06.004
- Oracle Cloud Always Free resources, https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
