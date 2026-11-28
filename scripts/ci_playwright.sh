#!/usr/bin/env bash
# Builds fresh demo data, starts the risk service and the API, and runs the Playwright checks.
# Used by CI and runnable locally. Offline: the demo is synthetic and no live source is called.
set -euo pipefail
PY="${PY:-.venv/bin/python}"
WORK="${WORK:-var/ci}"
OUT="${OUT:-var/screens}"
rm -rf "$WORK" && mkdir -p "$WORK"
"$PY" -m candleisgreen.demo --workdir "$WORK" > "$WORK/demo.log" 2>&1
"$PY" -m candleisgreen.risk.service --port 8765 --state-dir "$WORK/risk" > "$WORK/risk.log" 2>&1 &
RISK=$!
"$PY" -m candleisgreen.api --workdir "$WORK" --risk-url http://127.0.0.1:8765 --port 8000 --mode manual_simulation > "$WORK/api.log" 2>&1 &
API=$!
trap 'kill $RISK $API 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8000/api/status > /dev/null && break
  sleep 1
done
node ui/scripts/screens.mjs http://127.0.0.1:8000 "$OUT"
