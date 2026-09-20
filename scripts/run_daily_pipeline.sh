#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    echo "Crie o ambiente com: python3.12 scripts/setup_environment.py" >&2
    exit 1
fi
exec .venv/bin/python -X utf8 -u run_daily_pipeline.py
