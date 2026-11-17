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
