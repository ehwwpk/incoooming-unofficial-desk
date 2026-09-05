#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
require_no_arguments "$@"

if [ ! -e .venv ] && [ ! -L .venv ]; then
    INCOOOMING_SELECTED_PYTHON=
    if [ -n "${INCOOOMING_PYTHON:-}" ]; then
        supported_python "$INCOOOMING_PYTHON" || fail "INCOOOMING_PYTHON must name one working Python 3.12, 3.13, or 3.14 executable."
        INCOOOMING_SELECTED_PYTHON=$INCOOOMING_PYTHON
    else
        for candidate in python3 python3.12 python3.13 python3.14; do
            if command -v "$candidate" >/dev/null 2>&1 && supported_python "$candidate"; then
                INCOOOMING_SELECTED_PYTHON=$candidate
                break
            fi
        done
    fi
    [ -n "$INCOOOMING_SELECTED_PYTHON" ] || fail "Install Python 3.12, 3.13, or 3.14 from python.org, reopen Terminal, and run this command again."
    "$INCOOOMING_SELECTED_PYTHON" -m venv .venv || fail "Python could not create .venv. Check that this folder is writable and Python is installed correctly."
elif [ -n "${INCOOOMING_PYTHON:-}" ]; then
    printf '%s\n' 'Reusing the existing .venv. INCOOOMING_PYTHON only chooses Python when creating a new environment.'
fi

require_venv
"$INCOOOMING_VENV_PYTHON" --version
"$INCOOOMING_VENV_PYTHON" -m pip install --upgrade pip
"$INCOOOMING_VENV_PYTHON" -m pip install -e '.[dev]'

printf '%s\n' 'Setup is complete.' \
    'Try the demo: sh scripts/run-demo.sh' \
    'Use your CSV files: sh scripts/run-local.sh' \
    'Only a live Schwab connection needs a .env file. See docs/getting-started-macos.md.'
