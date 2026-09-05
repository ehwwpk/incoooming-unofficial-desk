#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
require_no_arguments "$@"
require_venv
"$INCOOOMING_VENV_PYTHON" -m ruff check .
"$INCOOOMING_VENV_PYTHON" -m ruff format --check .
"$INCOOOMING_VENV_PYTHON" -m mypy src
"$INCOOOMING_VENV_PYTHON" -m pytest -p no:cacheprovider
