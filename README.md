# CandleIsGreen

An evidence-driven quantitative research workstation. Paper trading only. No code path can place a live order.

Start with `SPEC.md` (v3.2). The review that produced v3.1 is `REVIEW.md`. Decisions waiting for Aditi are in `QUESTIONS.md`. Current state and the next step are in `HANDOFF.md`.

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

`make ci` runs every test. `make phase0` pushes one recorded event through the whole chain and prints the IDs.

To see the Phase 1 screens on the offline synthetic market:

```bash
make demo
```

Then open http://127.0.0.1:8000. Every number in the demo is synthetic. `make screens` checks both screens with Playwright.

With Alpaca paper keys in `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`, the recorder runs against the real free data:

```bash
.venv/bin/python -m candleisgreen.jobs catch-up --workdir var/live
```

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
| Hosting | Oracle Cloud Always Free, never upgraded, with a local fallback | Free |
| US prices and paper trading | Alpaca free plan | Free |
| US history with delisted stocks | Survivorship-aware forward recorder from Phase 1, plus free portfolio returns built from CRSP for research | Free |
| Filings, macro, papers | SEC EDGAR, FRED, BLS, BEA, Crossref, OpenAlex free key, arXiv | Free |
| News | Lawful RSS feeds | Free |
| AI | Optional local open-weight model, off by default | Free |

What the platform cannot do without paid data is listed, with reasons, in `config/capabilities.yaml`.
