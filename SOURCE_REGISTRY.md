# SOURCE_REGISTRY.md

Source: `SPEC.md` v3.2, sections "Source registry and expert discovery" and "Data contract". Every data source, its license, what it may be used for, and its status. No subscription or monthly fee, ever (principle 11).

## Data sources

| Source | What | License ID (`config/licenses.yaml`) | Research | Paper trading | Status |
| --- | --- | --- | --- | --- | --- |
| Alpaca free plan | Asset list, daily consolidated bars (15 minutes delayed), corporate actions, IEX real-time quotes, paper trading | `alpaca_market_data` | Permitted | Permitted | Built against an offline fake. Live run needs paper keys |
| SEC EDGAR | Submissions, XBRL company facts, SIC codes, filing acceptance times | `us_government_public` | Permitted | Permitted | Built. Live run needs `SEC_USER_AGENT` |
| SEC and Federal Reserve RSS | Press releases and litigation releases | `us_government_public` | Permitted | Permitted | Built |
| FRED | Daily FX (H.10), public CSV endpoint. Macro series with every vintage through the FRED API `series/observations` (realtime 1776-07-04 to 9999-12-31), key in `FRED_API_KEY` | `fred_terms` (H.10 FX series are public domain, citation requested) | Permitted | Unverified for other series | FX built. Macro built and tested on a constructed fixture. First run with a key must compare response shapes |
| ClinicalTrials.gov | API v2 `studies`, no key, latest version of each study only, so trials are recorded forward as snapshots | `clinicaltrials_gov` | Permitted | Unverified. Terms page did not render for automated reading | Built and tested on a constructed fixture. Live API response checked on 2026-11-24 |
| Open Source Asset Pricing | Long-short portfolio returns and signal documentation | `cc_by_4_0` | Permitted | Permitted | Built, release 2026.10 |
| JKP Global Factor Data | Factor returns by country | `cc_by_nc_4_0` | Permitted | Unverified, so research only | Built |
| Kenneth French library | Factor returns, Fama-French 12 SIC mapping | `french_library` | Permitted | Unverified | SIC mapping built |
| QuantConnect | Outside exploration only | none | Not connected | Not connected | Never a dependency, no data extracted |

## Not available, kept in the architecture

Options data, intraday consolidated data, analyst consensus estimates, licensed news and non-US execution. Reasons are in `config/capabilities.yaml`.

## People and institutions

People enter only through the same pipeline as any source (spec principle 7). A source profile records `identity_status`, `domain_evidence`, `claim_testability`, `track_record`, `conflicts`, `latency` and `evidence_label`. A regulatory record attaches to a person only when two strong identifiers match (CRD number, firm, or a filing naming both). A name and city match alone stays `possible_match_unresolved` for Aditi to review. BrokerCheck lookups are manual, because its permitted uses exclude feeding a trading system.

Practitioner claims are scored in `candleisgreen/research/practitioners.py`: hit rate with a Wilson interval against a 50% baseline, and the Brier score when a probability was stated. A domain becomes a signal only after 30 scored claims (provisional) and an interval above the baseline. Fame, followers and reputation carry no weight.

Status: practitioner scoring is built. Discovery queries, identity matching and the Experts screen are not built yet.

## Claim card schema

`claim_id`, `source_id`, `source_type`, `canonical_url`, `doi`, `title`, `author_ids`, `published_at`, `revised_at`, `ingested_at`, `first_actionable_at`, `market`, `instruments`, `target`, `horizon`, `direction`, `probability_if_stated`, `definition`, `mechanism`, `data_required`, `code_available`, `peer_review_status`, `replication_links`, `conflicts`, `license`, `test_plan_id`, `evidence_status`, `capture_hash`. Built in `candleisgreen/research/registry.py` as a JSON card with a content-derived ID.
