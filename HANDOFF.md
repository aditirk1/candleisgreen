# HANDOFF.md

Last updated: 2026-11-17 01:35 ET. Branch: `spec-review-and-phase0`.

## Done

1. **Review pass.** `REVIEW.md` holds errors, outdated facts, disagreements and open questions, each with a verification status.
2. **Spec v3.1.** `SPEC.md` (renamed from `spec.md`) has every technical fix from the review applied, with a change log at the end. Hard risk limits were not changed. Decisions that need Aditi are in `QUESTIONS.md` with the default in use.
3. **Documents.** `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RISK_POLICY.md`, `MODEL_REGISTRY.md`.
4. **Phase 0.** Both acceptance tests pass: one offline event flows end to end with immutable IDs, and a planted lookahead leak is caught. 69 tests pass. Details in `TEST_RESULTS.md`.

## Half done

- **Composite module (spec section C).** Not started at the time of this entry. See "Exact next step".

## Not started

- Phase 1 and later. No network call, broker account or UI exists.
- `SOURCE_REGISTRY.md`, `RESEARCH_PROTOCOL.md`, `DESIGN_SYSTEM.md`.

## Commands

```bash
make setup
```

```bash
make ci
```

```bash
make phase0
```

## Known flaws

- The risk engine runs in-process. The spec wants a separate process. The message types are ready for that move (DECISIONS D-007).
- The daily loss stop blocks buys and allows sells that reduce risk (DECISIONS D-009). Aditi should confirm.
- The cluster mapping for the 20% limit does not exist. The caller must supply `cluster_value`, and a missing value blocks the order.
- Tests ran on Python 3.13 only.
- Some review facts are still unverified. They are listed in `REVIEW.md` section 5.

## Exact next step

Build `candleisgreen/composite/` to the interface in `ARCHITECTURE.md` section 3.6, in this order, with a test file per step: `edge.py` (C.4, check against the C.11 worked example: 3.04%, 1.44%, 0.98), `eligibility.py` (C.5), `standardize.py` (C.2), `weights.py` (C.6), `combine.py` (C.7), `optimizer.py` (C.8), `run.py` (C.10), then the C.12 tests.
