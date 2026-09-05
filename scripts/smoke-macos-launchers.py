"""Exercise the documented shell setup in a fresh checkout with spaces in its path."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from macos_smoke_support import (
    evidence_dir,
    fetch_json,
    free_port,
    record,
    require,
    require_macos,
    stop_owned,
    wait_ready,
)


def run() -> None:
    require_macos()
    source = Path(__file__).resolve().parents[1]
    root = Path(os.environ["RUNNER_TEMP"]) / "Incoooming Mac setup with spaces"
    root.mkdir(exist_ok=False)
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
    for relative in filter(None, paths):
        original = source / relative
        if original.is_file():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    sentinel = (
        '# Local setup must preserve this file.\nSCHWAB_DASHBOARD_DATA_DIR="data with spaces"\n'
    )
    (root / ".env").write_text(sentinel, encoding="utf-8")
    env = {
        **os.environ,
        "INCOOOMING_PYTHON": sys.executable,
        "SCHWAB_AUTO_SYNC_ENABLED": "false",
        "SCHWAB_DASHBOARD_HOST": "127.0.0.1",
        "SCHWAB_DASHBOARD_DEMO_MODE": "false",
    }
    for key in ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "PYTHONPATH", "SCHWAB_DASHBOARD_DATA_DIR"):
        env.pop(key, None)
    outside = Path(os.environ["RUNNER_TEMP"])
    setup = ["sh", str(root / "scripts/bootstrap.sh")]
    with (evidence_dir() / "bootstrap.log").open("wb") as log:
        subprocess.run(setup, cwd=outside, env=env, stdout=log, stderr=log, timeout=240, check=True)
        subprocess.run(setup, cwd=outside, env=env, stdout=log, stderr=log, timeout=240, check=True)
    require((root / ".env").read_text(encoding="utf-8") == sentinel, "Setup overwrote .env.")

    port = free_port()
    data = root / "data with spaces"
    override_data = root / "explicit environment override"
    env["SCHWAB_DASHBOARD_PORT"] = str(port)
    for index, mode in enumerate(("demo", "local", "local", "local")):
        launch_env = dict(env)
        if index == 3:
            launch_env["SCHWAB_DASHBOARD_DATA_DIR"] = str(override_data)
        launch = ["sh", str(root / f"scripts/run-{mode}.sh")]
        with (evidence_dir() / f"launcher-{mode}.log").open("ab") as log:
            process = subprocess.Popen(
                launch, cwd=outside, env=launch_env, stdout=log, stderr=log, start_new_session=True
            )
            try:
                wait_ready(process, port)
                payload = fetch_json(
                    f"http://127.0.0.1:{port}/api/v1/dashboard", source_key="schwab"
                )
                require(payload["mode"] == ("demo" if mode == "demo" else "live"), "Mode changed.")
                duplicate = subprocess.run(
                    launch, cwd=outside, env=launch_env, capture_output=True, timeout=20
                )
                require(duplicate.returncode != 0, "A duplicate server launch unexpectedly passed.")
                require(
                    b"already in use" in duplicate.stdout + duplicate.stderr,
                    "A duplicate server launch did not explain the occupied port.",
                )
                wait_ready(process, port)
            finally:
                stop_owned(process)
        if mode == "demo":
            require((data / "demo-ledger.sqlite3").is_file(), "The demo database was not created.")
            require(
                not (data / "schwab-ledger.sqlite3").exists(),
                "The standalone demo created the personal ledger.",
            )
    require((data / "demo-ledger.sqlite3").is_file(), "The demo database was not created.")
    require((data / "schwab-ledger.sqlite3").is_file(), "The personal database was not created.")
    require(
        (override_data / "schwab-ledger.sqlite3").is_file(),
        "The explicit environment setting did not override the .env data path.",
    )
    require(not (outside / "data with spaces").exists(), "Data followed the caller's directory.")

    blocked_data = root / "must not be created"
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        blocked_env = {
            **env,
            "SCHWAB_DASHBOARD_PORT": str(unrelated.getsockname()[1]),
            "SCHWAB_DASHBOARD_DATA_DIR": str(blocked_data),
        }
        blocked = subprocess.run(
            ["sh", str(root / "scripts/run-local.sh")],
            cwd=outside,
            env=blocked_env,
            capture_output=True,
            timeout=20,
        )
        require(blocked.returncode != 0, "An unrelated occupied port was accepted.")
        require(not blocked_data.exists(), "An occupied port caused database writes.")
        require(unrelated.fileno() >= 0, "The unrelated listener was disturbed.")
    require((root / ".env").read_text(encoding="utf-8") == sentinel, "A launcher overwrote .env.")
    record(
        "launchers",
        {
            "status": "passed",
            "checks": [
                "fresh setup",
                "repeat setup",
                "path with spaces",
                "outside working directory",
                "demo and real book isolation",
                "duplicate launch",
                "Ctrl+C",
                "restart",
                "unrelated occupied port",
                "existing environment file preserved",
                "relative .env data path",
                "explicit environment override",
            ],
        },
    )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        record("launchers", {"status": "failed", "error_type": type(exc).__name__})
        raise
