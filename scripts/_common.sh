#!/bin/sh
# Sourced by the launchers; paths stay relative to this checkout, not the caller.
set -eu

INCOOOMING_PROJECT_ROOT=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
cd "$INCOOOMING_PROJECT_ROOT"
INCOOOMING_VENV_PYTHON="$INCOOOMING_PROJECT_ROOT/.venv/bin/python"

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

require_no_arguments() {
    [ "$#" -eq 0 ] || fail "This launcher takes no arguments. Configure the local .env file instead."
}

supported_python() {
    "$1" -c 'import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 15) else 1)' >/dev/null 2>&1
}

require_venv() {
    [ -x "$INCOOOMING_VENV_PYTHON" ] || fail "The Mac Python environment is missing or unusable. Run: sh \"$INCOOOMING_PROJECT_ROOT/scripts/bootstrap.sh\". A .venv copied from another computer cannot be reused."
    supported_python "$INCOOOMING_VENV_PYTHON" || fail "The existing .venv needs a working Python 3.12, 3.13, or 3.14. It was left unchanged. Move it aside yourself, then run bootstrap.sh again."
    "$INCOOOMING_VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1 || fail "The .venv interpreter is not running inside a virtual environment. It was left unchanged. Move it aside yourself, then run bootstrap.sh again."
}
