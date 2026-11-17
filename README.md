# CandleIsGreen

An evidence-driven quantitative research workstation. Paper trading only. No code path can place a live order.

Start with `SPEC.md` (v3.1). The review that produced v3.1 is `REVIEW.md`. Decisions waiting for Aditi are in `QUESTIONS.md`. Current state and the next step are in `HANDOFF.md`.

## Run it

```bash
make setup
```

```bash
make ci
```

```bash
make phase0
```

`make ci` runs every test. `make phase0` pushes one recorded event through the collector, the point-in-time store, a stub model, the risk engine and the internal simulator, and prints the IDs.

## Documents

| File | Content |
| --- | --- |
| `SPEC.md` | Product spec v3.1 |
| `REVIEW.md` | Review of spec v3: errors, outdated facts, disagreements, open questions |
| `QUESTIONS.md` | Decisions for Aditi with the default in use |
| `ARCHITECTURE.md` | Services, interfaces, config layout |
| `DATA_DICTIONARY.md` | Every schema, field by field |
| `RISK_POLICY.md` | Hard limits and how each is enforced |
| `MODEL_REGISTRY.md` | Models, signals, tiers and their status |
| `DECISIONS.md` | Choices made where the spec was silent |
| `TEST_RESULTS.md` | What ran and passed |
| `HANDOFF.md` | Working state, commands, next task |

Not written yet: `SOURCE_REGISTRY.md`, `RESEARCH_PROTOCOL.md`, `DESIGN_SYSTEM.md`.

## Estimated monthly cost

Nothing is being paid for today. Everything runs offline on fixtures.

| Item | Option | Cost | Status |
| --- | --- | --- | --- |
| Hosting | Hetzner CX23, 2 vCPU and 4 GB | EUR 5.99 per month | Not started |
| Hosting | DigitalOcean or AWS Lightsail, same size | $24 per month | Alternative |
| US history with delisted stocks | Sharadar Bundle Full History | $499 per year | Needs Aditi's decision |
| Real-time consolidated quotes | Alpaca Algo Trader Plus | $99 per month | Not recommended yet |
| AI for claim cards and digests | Optional, budget-capped | Set by Aditi | Not built |

Prices were read on 2026-11-17. Sources are in `REVIEW.md`.
