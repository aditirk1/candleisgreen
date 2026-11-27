# QUESTIONS.md: decisions that belong to Aditi

## Standing rules

- **No subscription-based platform and no monthly fee, ever** (2026-11-17). Spec principle 11.
- **Evidence, safeguards and settings are kept apart** (2026-11-22). Every config value is classified in `config/parameters.yaml` as empirical, safeguard, provisional or external fact. Research thresholds are provisional defaults, not hard rules. Spec principle 12 and the Parameter basis section.

## Decided on 2026-11-22

Each decision is written out in `SPEC.md`, section "Decisions register (v3.2)", with its assumptions, implementation, validation test and failure behavior.

| ID | Decision in short |
| --- | --- |
| Q1 | Three free sources. The forward universe is survivorship-aware, not automatically survivorship-free, and keeps historical asset IDs, corporate actions, delistings, inactive securities and completeness flags. Academic evidence never substitutes for stock-level implementation tests |
| Q3 | JKP for noncommercial academic and personal research only. Data and derived results tagged by license. Trading use not assumed authorized |
| Q4 | Next-session paper limit orders inside a configurable window, initially 09:35 to 10:30 ET. Quote-quality, spread and participation checks. No execution without fresh execution-grade data, and delayed consolidated prices never count. Slippage measured and windows compared before a permanent default |
| Q5 | Provisional $5 and $10M filters from decision-time information, plus spread, halt and liquidity checks. Separate research-only biotech universe |
| Q6 | Infrastructure failure pauses trading at once. Strategy deterioration judged against the forecast distribution with sample uncertainty. No universal 252-day 5th-percentile rule |
| Q7 | Fama-French sector limits plus correlation clusters, 20% cluster cap configurable. Stability tested, pending orders counted, overlapping classifications cannot bypass limits |
| Q8 | 63-trading-day minimum shadow period plus per-strategy trade-count and precision requirements. Shadow trading starts when the implementation is ready |
| Q9 | Walk-forward reconstruction allowed with point-in-time inputs, development history stored, labeled retrospective and never treated as a prospective test |
| Q10 | SIC mapped to Fama-French 12 with classification dates and mapping versions. Unknowns cannot evade limits |
| Q11 | Python 3.13, 3.12 where feasible, 3.14 only after a full check |
| Q12 | Package layout accepted, with tested module boundaries |
| Q13 | Oracle Cloud Always Free preferred, local execution and scheduled-task fallback. Oracle's own pages (checked 2026-11-22) document idle-instance reclamation, capacity shortages and a fixed home region, so every job must be safe to rerun and catch up, and the account must never be upgraded |
| Q14 | Academic evidence supports hypotheses, never certifies an implementation. Promotion needs an executable approximation, realistic costs and prospective validation |
| Q15 | QuantConnect optional and outside only. No dependency, no data extracted |

Q2 was closed on 2026-11-17 by the no-subscription rule: the free IEX feed only.

## Still open

- Hard limit values in the risk table. Defaults are in `config/default.yaml` under `risk.hard_limits`, classified as safeguards and unchanged.
- Tax professional review before any foreign fund or non-US holding. This only matters if non-US holdings ever come back into scope.

## Not available, kept in the architecture

These have no adequate free data and show NOT AVAILABLE with the reason, from `config/capabilities.yaml`: options data and options flow, intraday trading, real-time consolidated quotes, analyst consensus estimates (so earnings beat or miss is never shown), licensed news, and non-US execution.
