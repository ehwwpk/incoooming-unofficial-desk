#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
. "$SCRIPT_DIR/_common.sh"

NO_BROWSER=false
NO_SYNC=false
NO_START=false
for argument in "$@"; do
    case "$argument" in
        --no-browser) NO_BROWSER=true ;;
        --no-sync) NO_SYNC=true ;;
        --no-start) NO_START=true ;;
        --help|-h)
            printf '%s\n' 'Usage: sh scripts/connect-schwab.sh [--no-browser] [--no-sync] [--no-start]'
            printf '%s\n' 'Log in through Schwab, save the connection, sync, and start Incoooming.'
            printf '%s\n' '--no-browser prints the login link for you to open.'
            printf '%s\n' '--no-sync skips the first sync and disables auto-sync for this launch.'
            printf '%s\n' '--no-start finishes after login and optional first sync.'
            exit 0
            ;;
        *) printf '%s\n' "Unknown option: $argument. Use --help for the available options." >&2; exit 2 ;;
    esac
done

require_venv
set --
if "$NO_BROWSER"; then set -- "$@" --no-browser; fi
if "$NO_SYNC"; then set -- "$@" --no-sync; fi
"$INCOOOMING_VENV_PYTHON" -m schwab_dashboard.cli auth-connect "$@"

if "$NO_START"; then exit 0; fi
if "$NO_SYNC"; then export SCHWAB_AUTO_SYNC_ENABLED=false; fi
exec sh "$SCRIPT_DIR/run-local.sh"
