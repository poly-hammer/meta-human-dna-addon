@echo off
setlocal
set "PYTHONWARNINGS=ignore"
uv run pytest --cov-branch --cov-config=.coveragerc --cov=src/addons/meta_human_dna --cov-report=xml:reports/coverage/results.xml
exit /b 0
