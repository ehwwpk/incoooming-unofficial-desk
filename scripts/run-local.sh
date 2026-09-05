#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
require_no_arguments "$@"
require_venv
exec "$INCOOOMING_VENV_PYTHON" -m schwab_dashboard.cli serve
