# RESEARCH_PROTOCOL.md

Source: `SPEC.md` v3.2, sections "Research pipeline", "Validation protocol" and the decisions register. How a claim becomes evidence, and what each step requires.

## The path of a claim

1. **Claim card.** Every paper, practitioner claim or platform pattern becomes a claim card (Tier 1).
2. **Duplicates and novelty.** The daily factory links a duplicate to the existing claim, and links a near-duplicate of a library signal to that signal. A claim that contradicts an active signal (Tier 2 or above) opens a re-evaluation case.
3. **Data check.** Missing data marks the claim NEEDS_DATA with a free substitute, never a paid one.
4. **Pre-registration.** The test plan and its decision rule are fixed and hashed before any test runs. A changed plan needs a new registration.
5. **Variants.** Every variant tried is recorded and counts in the trial registry. Experiments may vary provisional and empirical parameters only, never safeguards or external facts.
6. **Result.** Passed and failed results are both kept. The failure archive is never emptied.
7. **Tiers.** Reproduction gives Tier 2, independent replication Tier 3 (academic evidence stops here), an executable approximation tested by the platform with realistic costs Tier 4 (shadow weight), and prospective validation Tier 5 (paper capital, Aditi approves). Demotion is automatic.

## Decision rules by study type

All provisional except the t of 3.0 for new factors, which is empirical and applies to that case only. Values are in `config/default.yaml` under `research` and `composite.eligibility`.

| Study type | Rule | Code |
| --- | --- | --- |
| Reproduction | Same sign, and inside the paper's interval or at least half its size | `research/academic.py` `reproduce` |
| Independent replication | Same sign and significant at 5% with Newey-West errors on new data, independence recorded | `research/academic.py` `replicate_after_cutoff` |
| New factor from the platform's own search | t above 3.0, and Benjamini-Yekutieli FDR under 5% across the full registry, and an untouched holdout | `research/criteria.py` `new_factor_passes` |
| Event study | Interval of mean abnormal return excludes zero with errors clustered by date | `research/criteria.py` `event_study` |
| Forecasting model | Beats its baseline at one-sided 5% (Clark-West if nested, Diebold-Mariano with the Harvey-Leybourne-Newbold correction otherwise) and holds in 2 of 3 subperiods | `research/criteria.py` `forecast_beats_baseline` |
| Economic test | Lower bound of the block-bootstrap 90% interval of net excess return above zero at double modeled costs | `composite/eligibility.py` `economic_test` |

## Records

- Retrospective walk-forward results are labeled RETROSPECTIVE and never pooled with prospective forecasts.
- Results on synthetic data are labeled SYNTHETIC, and on Alpaca history before the forward record SURVIVORSHIP-BIASED. Neither can pass a gate that grants capital.
- Data and derived results keep their license tags.

## Monitoring

Infrastructure failures pause trading at once. Strategy deterioration is judged against the forecast distribution with sample uncertainty (`composite/monitoring.py`). An alert demotes one tier and opens a re-evaluation case (`research/monitor.py`).
