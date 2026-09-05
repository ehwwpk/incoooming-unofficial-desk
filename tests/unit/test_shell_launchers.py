from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="native POSIX launcher tests")
SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "Incoooming checkout with spaces"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in ("_common.sh", "bootstrap.sh", "run-local.sh", "run-demo.sh", "verify.sh"):
        shutil.copy2(SCRIPTS_ROOT / name, scripts / name)
    (root / ".env").write_text("SCHWAB_DASHBOARD_DATA_DIR=private ledger\n", encoding="utf-8")
    return root


def run_script(checkout: Path, name: str, *args: str, **environment: str):
    env = os.environ.copy()
    env.pop("INCOOOMING_PYTHON", None)
    env.update(environment)
    return subprocess.run(
        ["/bin/sh", str(checkout / "scripts" / name), *args],
        cwd=checkout.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_bootstrap_rejects_an_explicit_unsupported_python_without_falling_back(
    checkout: Path,
) -> None:
    unsupported = checkout.parent / "unsupported python"
    unsupported.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    unsupported.chmod(0o755)
    before = file_snapshot(checkout)

    result = run_script(checkout, "bootstrap.sh", INCOOOMING_PYTHON=str(unsupported))

    assert result.returncode == 1
    assert "INCOOOMING_PYTHON must name one working Python" in result.stderr
    assert file_snapshot(checkout) == before
    assert not (checkout / ".venv").exists()


def test_bootstrap_preserves_a_foreign_windows_virtual_environment(checkout: Path) -> None:
    foreign = checkout / ".venv" / "Scripts"
    foreign.mkdir(parents=True)
    (foreign / "python.exe").write_bytes(b"a Windows environment must not be replaced")
    before = file_snapshot(checkout)

    result = run_script(checkout, "bootstrap.sh")

    assert result.returncode == 1
    assert "copied from another computer cannot be reused" in result.stderr
    assert file_snapshot(checkout) == before
    assert not (checkout / ".venv" / "bin").exists()


def test_bootstrap_preserves_a_broken_virtual_environment_symlink(checkout: Path) -> None:
    broken = checkout / ".venv"
    broken.symlink_to(checkout.parent / "missing environment", target_is_directory=True)
    before = file_snapshot(checkout)

    result = run_script(checkout, "bootstrap.sh")

    assert result.returncode == 1
    assert "missing or unusable" in result.stderr
    assert broken.is_symlink()
    assert file_snapshot(checkout) == before


def test_bootstrap_preserves_an_existing_unsupported_environment(checkout: Path) -> None:
    interpreter = checkout / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    interpreter.chmod(0o755)
    before = file_snapshot(checkout)

    result = run_script(checkout, "bootstrap.sh")

    assert result.returncode == 1
    assert "existing .venv needs a working Python" in result.stderr
    assert "left unchanged" in result.stderr
    assert file_snapshot(checkout) == before


@pytest.mark.parametrize("name", ["bootstrap.sh", "run-local.sh", "run-demo.sh", "verify.sh"])
def test_shell_helpers_reject_unused_arguments_before_doing_work(checkout: Path, name: str) -> None:
    before = file_snapshot(checkout)

    result = run_script(checkout, name, "--unexpected")

    assert result.returncode == 1
    assert "takes no arguments" in result.stderr
    assert file_snapshot(checkout) == before
    assert not (checkout / ".venv").exists()
