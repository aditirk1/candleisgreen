# QUESTIONS.md: decisions that belong to Aditi

## Standing rule

**No subscription-based platform and no monthly fee, ever.** Set by Aditi on 2026-11-17. Any option that needs a subscription or a recurring fee is excluded. It is not offered as an alternative and not recommended later. Everything below uses free data, free tools and free accounts only.

Each open question has a recommended answer. Spec v3.1 and the code use the recommendation as the default until you answer. Reasoning and sources are in `REVIEW.md` under the same IDs.

## Open questions

| ID | Question | Recommended answer, used as the default | What changes if you say otherwise |
| --- | --- | --- | --- |
| Q1 | How do we get survivorship-free US data with no subscription? | Free datasets by purpose. (1) **Edge, from day one.** Open Source Asset Pricing portfolio returns (CC BY 4.0) and the Kenneth French library are built from CRSP, which includes delisted stocks. Every year after a factor's selection cutoff is out of sample, so Tiers 2 to 4 can be judged now at the portfolio level. (2) **Implementation, from the recorder's first day.** A Phase 1 collector saves the full Alpaca asset list and daily consolidated bars after each close, for your own use only. That record is survivorship-free from its first day and feeds the 63-day Tier 5 shadow, so the first paper position can come about three months after it starts. (3) **Older stock-level history** from Alpaca (2016 onward) stays labeled SURVIVORSHIP-BIASED and is screening only | Starting the recorder later delays the first paper position by the same amount |
| Q3 | JKP data is licensed non-commercial. Is personal paper trading inside that? | Treat it as allowed for research now. Re-check before any real-money project | If not allowed, JKP is dropped and replication on non-US data waits |
| Q4 | When do orders execute? | Sliced by the platform from 09:35 to 10:30 ET the next session | The opening auction needs an exception to two safety invariants (market closed, quote older than 15 seconds). I did not make one |
| Q5 | Biotech names under $5 or under $10M daily volume | Keep the filter for the tradable book. Allow a research-only biotech universe with lower filters | Lowering the tradable filter raises cost and gap risk |
| Q6 | What counts as failing monitoring? | Trailing 252-day net return below the 5th percentile of its expected distribution, or the feed unhealthy for 5 trading days | A stricter rule demotes faster and trades less |
| Q7 | How is a correlated cluster defined for the 20% hard limit? | Hierarchical clusters on 252-day residual return correlation, cut at 0.5, recomputed monthly. The 20% value is unchanged | Sector could be used as the cluster instead, which is simpler and coarser |
| Q8 | Length of the Tier 5 shadow period | 63 trading days | Longer is safer and delays the first paper position |
| Q9 | May the Composite's history be backfilled by walk-forward? | Yes, with point-in-time inputs and weights only, labeled as backfill | Without it the calibration check needs more than a year of live running before any paper order |
| Q10 | Sector scheme | SEC SIC codes mapped to Fama-French 12 industries. Both are free | None. GICS needs a paid licence and is excluded by the standing rule |
| Q11 | Python version | 3.14 as the target, 3.12 as the minimum. This container runs 3.13 and the tests pass there | None expected |
| Q12 | Package layout | One Python package `candleisgreen/` holding `sources`, `data`, `research`, `models`, `composite`, `backtests`, `risk`, `broker` and `core`. `ui/`, `tests/` and `config/` sit at the top | Top-level packages named `data` or `tests` collide with other libraries |
| Q14 | Accept portfolio-level out-of-sample evidence for Tier 4? | Yes, with conservative modeled costs, because those portfolios include small names the platform will not trade. The Tier 5 shadow then checks that the tradable stock-level version tracks it | Without this, Tier 4 waits a year for 252 days of the forward record |
| Q15 | Use QuantConnect? | Only as an optional outside tool for your own exploration. Nothing from it enters the evidence pipeline, and its terms were not verified | None for the platform |
| Q13 | Where do the scheduled jobs run? | Your own computer. If it is off at 16:30 ET, the job catches up on its next run: daily bars can be fetched again later, and an asset list snapshot taken late is marked with the time it was actually taken | A machine that is always on avoids gaps. Free-tier cloud servers exist but I have not verified any. Only one with no charge at all would qualify |

## Not available, kept in the architecture

These have no adequate free data. They stay in the design and show NOT AVAILABLE with the reason, from `config/capabilities.yaml`: options data and options flow, intraday trading, real-time consolidated quotes, analyst consensus estimates (so earnings beat or miss is never shown), licensed news, and non-US execution.

## Closed by the standing rule

| ID | Was | Now |
| --- | --- | --- |
| Q2 | Pay for Alpaca's full real-time data plan? | No. The free IEX feed only. The 15 second staleness limit and the 0.5% spread limit will block some names, and that is the correct fail-closed result |
| Old Q1 | Buy a paid survivorship-free dataset? | No. Replaced by the free plan in the new Q1 |
| Hosting | Rent a small cloud server? | No. See Q13 |
| AI budget | Monthly budget for a paid LLM? | Zero. AI features are optional, off by default, and use a locally hosted open-weight model only |
| News provider | A licensed news API after the RSS phase? | No. Lawful RSS feeds only, permanently |
| Global execution | Interactive Brokers with per-exchange market data fees? | No. Those fees are monthly. Phase 6 becomes global research only, using free factor returns. No non-US orders |

## Still open from spec v3, unchanged

- Hard limit values in the risk table. The defaults are in `config/default.yaml` under `risk.hard_limits` and were not changed.
- Tax professional review before any foreign fund or non-US holding. This only matters if non-US holdings ever come back into scope.
