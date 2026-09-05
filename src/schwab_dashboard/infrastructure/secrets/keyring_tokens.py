from __future__ import annotations

import sys

import keyring
from keyring.backend import KeyringBackend
from pydantic import ValidationError

from schwab_dashboard.application.errors import CredentialStoreError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.infrastructure.runtime.platform_commands import dashboard_command


class KeyringTokenStore:
    def __init__(self, *, service_name: str, account_name: str) -> None:
        self._service_name = service_name
        self._account_name = account_name

    def load(self) -> OAuthTokenSet | None:
        serialized = self._read(self._backend())
        if serialized is None:
            return None
        try:
            token = OAuthTokenSet.model_validate_json(serialized)
            # A manually edited or older entry may parse but still be unusable.
            if not token.access_token.strip() or token.issued_at.tzinfo is None:
                raise ValueError("Invalid stored token")
            return token
        except (ValidationError, ValueError):
            raise CredentialStoreError(
                "The saved Schwab connection could not be read. From the project folder, run "
                f"`{dashboard_command('auth-clear')}`, then "
                f"`{dashboard_command('auth-connect')}` to reconnect."
            ) from None

    def save(self, token: OAuthTokenSet) -> None:
        backend = self._backend()
        try:
            backend.set_password(
                self._service_name,
                self._account_name,
                token.model_dump_json(),
            )
        except (keyring.errors.KeyringError, OSError):
            raise CredentialStoreError(
                f"The Schwab connection could not be saved in {_storage_name()}. "
                f"{_recovery_hint()} Then, from the project folder, run "
                f"`{dashboard_command('auth-connect')}` again."
            ) from None

    def delete(self) -> None:
        backend = self._backend()
        # Read the raw entry so a corrupt token can still be removed. Do not
        # mistake a denied deletion for an already-absent credential.
        if self._read(backend) is None:
            return
        try:
            backend.delete_password(self._service_name, self._account_name)
        except keyring.errors.PasswordDeleteError:
            if self._read(backend) is None:
                return
            raise self._delete_error() from None
        except (keyring.errors.KeyringError, OSError):
            raise self._delete_error() from None

    def _backend(self) -> KeyringBackend:
        try:
            backend = keyring.get_keyring()
            usable = backend.priority > 0
            # Mac support means native Keychain storage. A user-level null or
            # third-party backend must not silently drop or write tokens to disk.
            if sys.platform == "darwin":
                from keyring.backends.macOS import Keyring

                usable = usable and isinstance(backend, Keyring)
            if not usable:
                raise keyring.errors.NoKeyringError()
            return backend
        except (keyring.errors.KeyringError, OSError, RuntimeError):
            raise CredentialStoreError(
                f"{_storage_name()} is not available for saving the Schwab connection. "
                "Check that Python keyring storage has not been disabled or replaced. "
                f"{_recovery_hint()} Demo and CSV imports still work."
            ) from None

    def _read(self, backend: KeyringBackend) -> str | None:
        try:
            return backend.get_password(self._service_name, self._account_name)
        except (keyring.errors.KeyringError, OSError):
            raise CredentialStoreError(
                f"The saved Schwab connection cannot be opened in {_storage_name()}. "
                f"{_recovery_hint()} Then retry. Demo and CSV imports still work."
            ) from None

    @staticmethod
    def _delete_error() -> CredentialStoreError:
        return CredentialStoreError(
            f"The saved Schwab connection could not be removed from {_storage_name()}. "
            f"{_recovery_hint()} Then, from the project folder, run "
            f"`{dashboard_command('auth-clear')}` again."
        )


def _storage_name() -> str:
    if sys.platform == "darwin":
        return "macOS Keychain"
    if sys.platform == "win32":
        return "Windows Credential Manager"
    return "your system credential store"


def _recovery_hint() -> str:
    if sys.platform == "darwin":
        return "Unlock your login keychain in Keychain Access and allow this Python to use it."
    return "Unlock your system credential store and allow this Python to use it."
