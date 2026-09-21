"""Exercise the shipped chart script with a small chart-library test double."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_performance_chart_interactions() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for chart interaction checks (installed in CI).")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_suffix(".cjs"))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
