"""Helpers for native macOS CI evidence, never customer account data."""

from __future__ import annotations

import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def evidence_dir() -> Path:
    directory = Path(os.environ["INCOOOMING_EVIDENCE_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def record(name: str, result: dict[str, object]) -> None:
    payload = {
        "commit": os.environ.get("GITHUB_SHA"),
        "runner_image": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "macos": platform.mac_ver()[0],
        "architecture": platform.machine(),
        "python": platform.python_version(),
        **result,
    }
    (evidence_dir() / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def require_macos() -> None:
    require(sys.platform == "darwin", "This smoke test must run on a native macOS runner.")
    expected = os.environ.get("INCOOOMING_EXPECTED_ARCH")
    require(expected in {"arm64", "x86_64"}, "A known native architecture must be specified.")
    require(platform.machine() == expected, "The runner did not use the requested architecture.")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch_json(url: str, *, source_key: str | None = None) -> dict[str, object]:
    headers = {"Cookie": f"incoooming_source={source_key}"} if source_key else {}
    with urlopen(Request(url, headers=headers), timeout=2) as response:
        return json.load(response)


def wait_ready(process: subprocess.Popen[bytes], port: int) -> dict[str, object]:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        require(process.poll() is None, "The local server exited before it became ready.")
        try:
            health = fetch_json(f"http://127.0.0.1:{port}/api/v1/health/ready")
            if health.get("app") == "incoooming-local-desk" and health.get("database") is True:
                return health
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.2)
    raise RuntimeError("The local server did not become ready within 35 seconds.")


def stop_owned(process: subprocess.Popen[bytes]) -> None:
    """Signal only the process group created by this smoke test."""
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        raise RuntimeError("The local server did not stop after Ctrl+C.") from None
    require(
        process.returncode in {0, 130, -signal.SIGINT}, "The local server stopped with an error."
    )


if __name__ == "__main__":
    require_macos()
    record("platform", {"status": "passed"})
