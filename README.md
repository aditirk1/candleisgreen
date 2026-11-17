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

## Cost

Zero. No subscription or monthly fee is used, ever (spec principle 11).

| Item | Choice | Cost |
| --- | --- | --- |
| Hosting | Aditi's own computer | Free |
| US prices and paper trading | Alpaca free plan | Free |
| US history with delisted stocks | Forward recorder from Phase 1, plus free portfolio returns built from CRSP | Free |
| Filings, macro, papers | SEC EDGAR, FRED, BLS, BEA, Crossref, OpenAlex free key, arXiv | Free |
| News | Lawful RSS feeds | Free |
| AI | Off | Free |
