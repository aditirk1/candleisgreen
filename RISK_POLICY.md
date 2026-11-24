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

A correlated cluster is defined in the spec as a hierarchical cluster on 252-day residual return correlation, cut at 0.5 and recomputed monthly (`QUESTIONS.md` Q7). The cluster mapping is planned. Until it exists the caller must supply `cluster_value`, and a missing value blocks the order.

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

The 24-hour loosening delay and the approval flow are planned. Today the only way to change a limit is to edit the config file through Git.

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
