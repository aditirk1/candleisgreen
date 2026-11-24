PY ?= .venv/bin/python

.PHONY: setup ci test phase0

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -e ".[dev]"

# The CI command. Runs every test, including the planted failure fixtures.
ci:
	$(PY) -m pytest

test: ci

# Runs one offline event end to end and prints the immutable IDs.
phase0:
	$(PY) -m candleisgreen.pipeline --fixture tests/fixtures/phase0_event.json --workdir var/phase0

# Offline demo on the synthetic market. Three terminals, or run `make demo` for all three.
demo-data:
	$(PY) -m candleisgreen.demo --workdir var/demo

risk:
	$(PY) -m candleisgreen.risk.service --port 8765 --state-dir var/demo/risk

api:
	$(PY) -m candleisgreen.api --workdir var/demo --risk-url http://127.0.0.1:8765 --port 8000 --mode manual_simulation

ui:
	cd ui && npm install && npx vite build

demo: demo-data ui
	$(PY) -m candleisgreen.risk.service --port 8765 --state-dir var/demo/risk & \
	$(PY) -m candleisgreen.api --workdir var/demo --risk-url http://127.0.0.1:8765 --port 8000 --mode manual_simulation

screens:
	node ui/scripts/screens.mjs http://127.0.0.1:8000 var/screens
