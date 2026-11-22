# CandleIsGreen
- The full product spec is SPEC.md (v3.2). Aditi's decisions are in its decisions register and summarized in QUESTIONS.md. Read the relevant section before any work.
- Paper trading only. No code path may ever place a live order.
- Build one phase at a time, in the order in SPEC.md. Do not start a phase until the previous one passes its acceptance test.
- Commit and update HANDOFF.md every 45 to 60 minutes of work.
- All thresholds and limits live in config files, never hard-coded. Each is classified in config/parameters.yaml as empirical, safeguard, provisional or external fact. Do not treat a provisional research threshold as a hard rule.
- No subscription or monthly fee, ever.
- UI text: no em dashes, semicolons, middle dots, filler or metaphors.
- Never commit API keys. Secrets come from environment variables only.
