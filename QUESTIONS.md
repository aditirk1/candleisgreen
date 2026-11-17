# QUESTIONS.md: decisions that belong to Aditi

Each question has a recommended answer. Spec v3.1 and the code use the recommendation as the default until you answer. Reasoning and sources are in `REVIEW.md` under the same IDs. Nothing here costs money until you say yes.

| ID | Question | Recommended answer, used as the default | What changes if you say otherwise |
| --- | --- | --- | --- |
| Q1 | Buy survivorship-free US data? | Yes, Sharadar Bundle Full History at $499 per year, after you read its terms page. Not bought yet. Until then every real signal is labeled SURVIVORSHIP-BIASED and stays at Tier 1, and the build runs on fixtures and synthetic data | Norgate Platinum at USD 630 per year is the alternative. It has index membership history and no fundamentals |
| Q2 | Pay $99 per month for Alpaca full real-time data? | No for now. Use the free IEX feed and fixtures | With the free feed the 15 second staleness limit and the 0.5% spread limit block many names. Paying widens the tradable set |
| Q3 | JKP data is licensed non-commercial. Is personal paper trading inside that? | Treat it as allowed for research now. Re-check before any real-money project | If not allowed, JKP is dropped and global factor research waits for another source |
| Q4 | When do orders execute? | Sliced by the platform from 09:35 to 10:30 ET the next session | The opening auction needs an exception to two safety invariants (market closed, quote older than 15 seconds). I did not make one |
| Q5 | Biotech names under $5 or under $10M daily volume | Keep the filter for the tradable book. Allow a research-only biotech universe with lower filters | Lowering the tradable filter raises cost and gap risk |
| Q6 | What counts as failing monitoring? | Trailing 252-day net return below the 5th percentile of its expected distribution, or the feed unhealthy for 5 trading days | A stricter rule demotes faster and trades less |
| Q7 | How is a correlated cluster defined for the 20% hard limit? | Hierarchical clusters on 252-day residual return correlation, cut at 0.5, recomputed monthly. The 20% value is unchanged | Sector could be used as the cluster instead, which is simpler and coarser |
| Q8 | Length of the Tier 5 shadow period | 63 trading days | Longer is safer and delays the first paper position |
| Q9 | May the Composite's history be backfilled by walk-forward? | Yes, with point-in-time inputs and weights only, labeled as backfill | Without it the calibration check needs more than a year of live running before any paper order |
| Q10 | Sector scheme | SEC SIC codes mapped to Fama-French 12 industries | GICS needs a paid licence |
| Q11 | Python version | 3.14 as the target, 3.12 as the minimum. This container runs 3.13 and the tests pass there | None expected |
| Q12 | Package layout | One Python package `candleisgreen/` holding `sources`, `data`, `research`, `models`, `composite`, `backtests`, `risk`, `broker` and `core`. `ui/`, `tests/` and `config/` sit at the top | Top-level packages named `data` or `tests` collide with other libraries |

## Still open from spec v3, unchanged

- Hard limit values in the risk table. The defaults are in `config/default.yaml` under `risk.hard_limits` and were not changed.
- News provider after the RSS phase.
- Hosting. Price points found: Hetzner CX23 at EUR 5.99 per month, DigitalOcean or AWS Lightsail at $24 per month.
- AI budget per month. List prices are in `REVIEW.md` O15.
- Order of non-US markets in Phase 6.
- Tax professional review before any foreign fund or non-US holding.
