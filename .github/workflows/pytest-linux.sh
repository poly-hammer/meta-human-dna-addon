#!/bin/bash
export PYTHONWARNINGS=ignore
export PYTHONPATH=src/addons/meta_human_dna/bindings/linux/x86_64
pytest --cov-config=.coveragerc --cov=src/addons/meta_human_dna --cov-report=xml:reports/coverage/results.xml
exit 0
