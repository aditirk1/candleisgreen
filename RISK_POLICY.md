# RISK_POLICY.md

Source: `SPEC.md` v3.2, section "Risk, execution and governance" and decisions Q4, Q6, Q7 and Q10. The limit values here are Aditi's. No code, model or document change may loosen them. This file restates them and says how each is enforced.

## 1. Scope

- Paper trading only. Venues are `SIMULATION` (internal simulator) and `PAPER` (broker paper account).
- Long-only US stocks and ETFs. No shorts, leverage, options or futures in the executable book.
- Live trading is not built. `execution.live_trading_enabled: true` fails config validation, the order schema has no live venue, `LiveBroker` raises on every call, and `assert_paper_endpoint` refuses any broker host other than `paper-api.alpaca.markets`.

## 2. Hard limits

Values live in `config/default.yaml` under `risk.hard_limits`. A test (`test_hard_limits_match_the_spec_defaults`) fails if any value changes without the test being changed with it.

| Limit | Default | Config key | Check in `risk/engine.py` |
| --- | --- | --- | --- |
| Max position size | 5% of equity | `max_position_pct_equity` | `position_size`: position value after the order, divided by equity |
| Max per correlated cluster | 20% of equity | `max_cluster_pct_equity` | `cluster`: cluster value after the order, divided by equity |
| Max order size | 1% of 20-day average daily volume | `max_order_pct_adv20` | `order_vs_adv`: order shares divided by ADV shares |
| Max bid-ask spread to trade | 0.5% | `max_spread_pct` | `spread`: (ask − bid) / mid |
| Daily loss stop | 2% of equity, halts new orders | `daily_loss_stop_pct_equity` | `daily_loss`: blocks buys when the loss from session start reaches the limit |
| Quote staleness | Over 15 seconds blocks the order | `max_quote_age_seconds` | `quote_fresh`: `now` − `quote_time` |
| Execution-grade feeds | IEX real time (and the fixture feed in tests). Delayed consolidated data may never be added | `execution_grade_feeds` | `quote_feed` |

Every value here is classified as a safeguard in `config/parameters.yaml`, so no experiment, search or optimizer can vary it.

Correlated clusters come from `candleisgreen/clusters.py` (decision Q7). Each month the overnight slot clusters residual daily returns (equal-weighted market removed) over `clustering.lookback_days` with average linkage, cut at `clustering.max_distance`. Every clustering setting is provisional.

- Stability is the adjusted Rand index against the last stable run. Below `clustering.min_stability` the run is UNSTABLE, orders use Fama-French 12 sectors as clusters with unknown sectors pooled, and Overview shows an alert.
- With no run yet, the same sector fallback applies.
- Under a stable run, if the order's name or any held or pending name has no cluster, cluster exposure cannot be computed and the order is blocked.
- `clusters.book_labels` gives a target book the same cluster keys, so `evaluate_portfolio` blocks a book with an unmapped name or a cluster over its cap. No code path sends an optimizer book to orders yet.
- The executor sums held and pending value in the order's cluster only. Before this job existed it summed the whole book, which was stricter.

### Short selling

Short selling is on. Aditi set the values on 2026-11-27 and waived the 24-hour wait for that one change (DECISIONS D-108). Three hard limits govern it, all Aditi's, and later changes go through the limit workflow:

| Limit | Default | Meaning |
| --- | --- | --- |
| `max_short_position_pct_equity` | 0.03 | Largest short in one stock, as a share of equity. 0 turns shorting off |
| `max_short_exposure_pct_equity` | 0.30 | All shorts together |
| `max_gross_exposure_pct_equity` | 1.0 | Longs plus absolute shorts. 1.0 means nothing is borrowed to trade |

Raising a short limit is a loosening: it waits `risk.loosening_delay_hours` and needs Aditi's second confirmation. Setting them back to 0 applies at once. The Audit and Rules screen has a Short selling card for this.

Every order is classed by what it does to the position. Orders that add risk (a buy that grows a long, a sale that opens or grows a short) face the position, short, gross, cluster and daily loss checks. Orders that reduce risk (selling a long, buying to cover a short) pass those checks even after the daily loss stop. A short also needs the broker to list the stock as shortable and easy to borrow, and an unknown borrow status blocks it. Hard-to-borrow stocks are never shorted, because they need a locate. One order can never turn a long into a short. The position is closed first and the short can open at the next decision. Clusters and sectors count longs and shorts together, by absolute value.

## 3. Order of checks

`evaluate(intent, context, limits)` runs every check, in this order, and approves only when all pass. It does not stop at the first failure, so the decision lists every reason.

1. `venue`: must be SIMULATION or PAPER
2. `kill_switch`: must be known and off
3. `market_open`: session must be known, open and not halted
4. `execution_window`: inside the configured window, initially 09:35 to 10:30 ET
5. `broker`: connection must be known and up
6. `account`: account state known, equity positive
7. `instrument`: symbol mapping certain
7a. `instrument_tag`: only `direct` or `proxy` instruments can receive orders. Every non-US instrument is `research_only`
8. `quote_fresh`: quote present, for this instrument, not older than the limit, not from the future
9. `quote_feed`: the feed is execution grade and neither side has zero size
10. `limit_price`: the limit is no further from mid than the spread limit
11. `spread`: not crossed, not wider than the limit
12. `daily_loss`: loss from session start under the stop (sells that reduce risk stay allowed)
13. `position_size`: no short positions, position plus pending buys within the limit after the order
14. `cluster`: cluster plus pending buys within the limit after the order
15. `order_vs_adv`: order within the participation limit

## 4. Fail-closed rules

- Orders are limit orders only (`execution.order_type: limit`). The simulator fills a limit only when it is marketable, and a resting limit is never converted to a market order.
- Infrastructure failure (missing critical data, invalid prices, a failed risk check) pauses the affected trading at once. Strategy deterioration is a separate, statistical question handled by monitoring (spec decision Q6).
- `evaluate_portfolio` checks the target book's sectors and clusters separately, so a name counts in both and neither can bypass the other. Names with a missing or blank sector share one UNKNOWN bucket under the sector cap.

- The optimizer's target book is checked by `evaluate_portfolio` before any order is built from it. Short positions, leverage, a position over its limit, a cluster over its limit, a name with no cluster mapping and a non-number weight each block the book. This is tested with a deliberately injected book.

- A missing input blocks the order. This is tested as a property over every combination of missing fields.
- An exception inside any check blocks the order with the reason "rule could not be evaluated".
- A stale quote, unknown account state, uncertain instrument mapping, closed or halted market, or disconnected broker each block the order.
- A broker adapter refuses any order without an `approved` decision for the same `client_order_id`.
- New strategies, data or model updates cannot change limits. The engine reads `HardLimits`, which is an immutable object loaded from config, and no module writes it.

## 5. Safety invariants

- The kill switch and the daily loss stop block new orders at once. Flattening positions is a separate action that depends on liquidity and the broker. It is never promised to be instant.
- Stop orders do not cap losses. Prices can gap through them.
- Orders carry stable client IDs derived from their content. After an uncertain broker response, open orders are queried before any retry. A resubmission with the same client ID is not executed twice (tested on the simulator).
- Positions and fills are reconciled with the broker after every order and at every session close (planned, Phase 2).
- Every order shows its evidence-linked rationale and data freshness. PAPER or SIMULATION shows on every order view.
- Orders are sent only in the regular session, 09:35 to 10:30 ET by default, so every order has a live quote. The opening auction is not used.
- A pre-open check at 09:00 ET may cancel orders and may never add them (planned).
- When the Composite is not calibrated the optimizer is reduce-only.

## 5a. Governance of evidence tiers

The system may raise a signal's tier up to 4 on recorded evidence. A promotion above Tier 4 is only a proposal until Aditi approves it, and `set_tier` refuses it from any other actor. Demotion after a failed re-evaluation or a drift alert is automatic and logged. No research job, model update or experiment can change a risk limit: experiments cannot vary safeguards, the risk service loads its own limits, and a test fingerprints every config file before and after a full research day.

## 6. Who can change what

| Change | Who | Guardrail |
| --- | --- | --- |
| Hard risk limits | Aditi only | Tightening applies now. Loosening waits 24 hours (`risk.loosening_delay_hours`) and asks again |
| Promote a signal to paper capital | System proposes, Aditi approves | Must hold Tier 5 with a complete experiment manifest |
| Composite weights | System, monthly | Change per weight limited to the larger of 25% of its value and 2 points, frozen benchmark always running |
| Demote or suspend a signal | System, automatically | Logged with the evidence that triggered it |
| New experiments | System, automatically | Sandbox only, no capital |
| Model code changes | Aditi or the coding model, through Git | Full test suite must pass |

The risk service owns limit changes (`candleisgreen/risk/limits.py`). The config file holds the base values and the service keeps active changes in its own state directory.

- Only `user:aditi` can request or confirm a change. Any other actor is refused.
- Every numeric limit is a ceiling, so a smaller value is a tightening and applies at once.
- A larger value waits in `pending` until `risk.loosening_delay_hours` has passed, then needs a second confirmation from Aditi.
- Fractional limits cannot exceed 1. Unknown keys and nonpositive values are refused.
- Each request and confirmation is written to the risk service's audit log.
- The workstation's Audit and Rules screen shows effective, base and pending values and sends requests through the risk service. It cannot write limits itself.

Pre-open check (`candleisgreen/preopen.py`): before the execution window, buy proposals still proposed or approved are cancelled when the instrument is halted, has a corporate action effective after the decision and by the session, or filed an 8-K since the decision. The check only cancels. It never adds or enlarges an order.

## 7. Operating modes

| Mode (`execution.mode`) | Orders | Default |
| --- | --- | --- |
| `research` | None | On |
| `teaching` | None | On |
| `manual_simulation` | Internal simulator after approval | On |
| `auto_simulation` | Internal simulator inside coded limits | On, the config default |
| `broker_paper_approval` | Paper account after each approval | After the integration test passes |
| `broker_paper_auto` | Paper account under per-strategy permission | After the integration test passes |
| Live, any form | Real money | Not built. Not a valid config value |

Switching modes never silently changes accounts, credentials or permissions.

## 8. Audit

Every signal, risk check, approval, order payload, broker response, status change, fill, cancellation and rule change is written to the audit log with UTC event time, received time, strategy version and actor. The log is append-only and hash-chained. `AuditLog.verify()` returns the first bad sequence number when any row was edited or removed.

## 9. What is tested today

See `TEST_RESULTS.md`. In short: each limit blocks at its boundary, each unknown blocks, a raising check blocks, the simulator refuses unapproved and duplicate orders, every live route raises, and a stale quote in the end-to-end flow produces a blocked decision with no fill.
