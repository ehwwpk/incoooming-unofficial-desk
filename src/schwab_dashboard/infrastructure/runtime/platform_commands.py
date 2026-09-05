from __future__ import annotations

import sys
from typing import Literal


def local_command(action: Literal["run-local", "run-demo", "connect-schwab"]) -> str:
    """Show commands for the computer running this local server."""
    if sys.platform == "win32":
        return f".\\scripts\\{action}.cmd"
    return f"sh ./scripts/{action}.sh"


def dashboard_command(command: str) -> str:
    """A checkout command that works without activating the Python environment."""
    if sys.platform == "win32":
        return f".\\.venv\\Scripts\\schwab-dashboard.exe {command}"
    return f"./.venv/bin/schwab-dashboard {command}"


def restart_instruction() -> str:
    if sys.platform == "win32":
        return ".\\scripts\\restart-local.cmd"
    return "Press Ctrl+C in the server Terminal, then run sh ./scripts/run-local.sh"


def demo_launcher_notice() -> str:
    return (
        "This server is running the fictional demo. To use CSV files or Schwab, "
        f"stop the demo with Ctrl+C, run {local_command('run-local')}, and open BOOK again."
    )
