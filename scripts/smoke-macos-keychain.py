"""Native CI only: disposable fake tokens through the application's real Keychain adapter."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import keyring
from keyring.backends.macOS import Keyring
from macos_smoke_support import record, require, require_macos

from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


def store_for(service: str) -> KeyringTokenStore:
    require(service.startswith("incoooming-ci-dummy-"), "Only disposable test items are allowed.")
    return KeyringTokenStore(service_name=service, account_name="ci-dummy-account")


def read_in_new_process(service: str, expected: str) -> None:
    require_macos()
    require(
        isinstance(keyring.get_keyring(), Keyring), "The native Apple Keychain was not selected."
    )
    token = store_for(service).load()
    require(
        token is not None and token.access_token == expected, "Stored dummy token did not match."
    )


def run() -> None:
    require_macos()
    require(
        isinstance(keyring.get_keyring(), Keyring), "The native Apple Keychain was not selected."
    )
    service = f"incoooming-ci-dummy-{uuid.uuid4()}"
    store = store_for(service)
    try:
        require(store.load() is None, "The unique dummy Keychain item already existed.")
        for revision in ("first", "updated"):
            dummy = f"INCOOOMING-CI-FAKE-{revision}"
            store.save(
                OAuthTokenSet(access_token=dummy, refresh_token="INCOOOMING-CI-FAKE-REFRESH")
            )
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--read", service, dummy],
                check=True,
                capture_output=True,
                timeout=30,
            )
    finally:
        # The unique service never overlaps the application's real token namespace.
        store.delete()
    require(store.load() is None, "The disposable Keychain item was not removed.")
    store.delete()
    record(
        "keychain",
        {
            "status": "passed",
            "backend": "macOS.Keyring",
            "checks": [
                "missing item",
                "save",
                "read in a fresh process",
                "update",
                "delete",
                "repeat delete",
            ],
            "scope": "Dummy tokens only; no real Schwab authorization or permission-dialog test.",
        },
    )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--read":
        read_in_new_process(sys.argv[2], sys.argv[3])
    else:
        try:
            run()
        except Exception as exc:
            record("keychain", {"status": "failed", "error_type": type(exc).__name__})
            # Native errors can contain provider details. The evidence needs only the type.
            raise SystemExit("Native Keychain smoke failed; see keychain.json.") from None
