#!/bin/bash
export PYTHONWARNINGS=ignore
uv run pytest --cov-branch --cov-config=.coveragerc --cov=src/addons/meta_human_dna --cov-report=xml:reports/coverage/results.xml
exit 0
