.PHONY: help test eval qualify check

# The package lives under src/. pytest picks this up from pyproject.toml;
# the plain-python targets need it on the path explicitly.
export PYTHONPATH := src

help:
	@echo "make test     - run the unit tests"
	@echo "make eval     - run the scenario suite against eval/transcripts"
	@echo "make qualify  - rank the example prospecting survey"
	@echo "make check    - test + eval (eval gates may legitimately be red)"

test:
	python -m pytest

eval:
	python -m dentaldesk.evaluate eval/transcripts

qualify:
	python -m dentaldesk.prospecting.qualify prospecting/example-surveys.csv

check: test eval
