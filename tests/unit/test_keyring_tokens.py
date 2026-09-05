from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import keyring
import pytest
from keyring.backend import KeyringBackend

from schwab_dashboard.application.errors import CredentialStoreError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.infrastructure.secrets import keyring_tokens
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


class FakeBackend(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.serialized: str | None = None
        self.read_error: Exception | None = None
        self.write_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.delete_race = False

    def get_password(self, service: str, username: str) -> str | None:
        if self.read_error:
            raise self.read_error
        return self.serialized

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.write_error:
            raise self.write_error
        self.serialized = password

    def delete_password(self, service: str, username: str) -> None:
        if self.delete_race:
            self.serialized = None
        if self.delete_error:
            raise self.delete_error
        self.serialized = None


@pytest.fixture()
def backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    fake = FakeBackend()
    monkeypatch.setattr(keyring, "get_keyring", lambda: fake)
    monkeypatch.setattr(keyring_tokens, "sys", SimpleNamespace(platform="win32"))
    return fake


def _store() -> KeyringTokenStore:
    return KeyringTokenStore(service_name="test-only-service", account_name="test-only-account")


def test_token_round_trip_refresh_update_and_delete(backend: FakeBackend) -> None:
    store = _store()
    assert store.load() is None
    token = OAuthTokenSet(access_token="dummy-access", refresh_token="dummy-refresh")
    store.save(token)
    assert store.load() == token
    updated = token.model_copy(update={"access_token": "dummy-updated"})
    store.save(updated)
    assert store.load() == updated
    store.delete()
    assert store.load() is None
    store.delete()


@pytest.mark.parametrize(
    "error",
    [
        keyring.errors.KeyringLocked("dummy-sensitive-detail"),
        keyring.errors.NoKeyringError("dummy-sensitive-detail"),
        OSError("dummy-sensitive-detail"),
    ],
)
def test_storage_read_errors_are_actionable_and_redacted(
    backend: FakeBackend, error: Exception
) -> None:
    backend.read_error = error
    with pytest.raises(CredentialStoreError) as caught:
        _store().load()
    assert "Windows Credential Manager" in str(caught.value)
    assert "Demo and CSV imports still work" in str(caught.value)
    assert "dummy-sensitive-detail" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_disabled_backend_does_not_claim_token_storage(
    backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend, "priority", 0)
    with pytest.raises(CredentialStoreError, match="not available"):
        _store().save(OAuthTokenSet(access_token="dummy-access"))
    assert backend.serialized is None


def test_mac_requires_native_keychain_backend(
    backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keyring_tokens, "sys", SimpleNamespace(platform="darwin"))
    with pytest.raises(CredentialStoreError, match="macOS Keychain"):
        _store().save(OAuthTokenSet(access_token="dummy-access"))
    assert backend.serialized is None


@pytest.mark.parametrize(
    "serialized",
    [
        "{dummy-sensitive-invalid-json",
        '{"access_token":""}',
        '{"access_token":"dummy-access","issued_at":"2026-08-07T00:00:00"}',
        '{"access_token":123}',
    ],
)
def test_corrupt_token_can_be_cleared_without_exposing_its_contents(
    backend: FakeBackend, serialized: str
) -> None:
    backend.serialized = serialized
    with pytest.raises(CredentialStoreError) as caught:
        _store().load()
    assert "auth-clear" in str(caught.value)
    assert "dummy" not in str(caught.value)
    _store().delete()
    assert backend.serialized is None


def test_failed_save_does_not_claim_success(backend: FakeBackend) -> None:
    backend.write_error = keyring.errors.PasswordSetError("dummy-sensitive-detail")
    with pytest.raises(CredentialStoreError, match="could not be saved") as caught:
        _store().save(OAuthTokenSet(access_token="dummy-access"))
    assert "dummy-sensitive-detail" not in str(caught.value)
    assert backend.serialized is None


def test_denied_delete_is_not_reported_as_success(backend: FakeBackend) -> None:
    backend.serialized = "dummy-corrupt-entry"
    backend.delete_error = keyring.errors.PasswordDeleteError("dummy-sensitive-detail")
    with pytest.raises(CredentialStoreError, match="could not be removed") as caught:
        _store().delete()
    assert "dummy-sensitive-detail" not in str(caught.value)
    assert backend.serialized == "dummy-corrupt-entry"


def test_delete_is_idempotent_if_another_process_removed_the_entry(backend: FakeBackend) -> None:
    backend.serialized = "dummy-corrupt-entry"
    backend.delete_error = keyring.errors.PasswordDeleteError("already absent")
    backend.delete_race = True
    _store().delete()
    assert backend.serialized is None


def test_token_with_timezone_can_be_checked_for_expiry(backend: FakeBackend) -> None:
    token = OAuthTokenSet(access_token="dummy-access", issued_at=datetime.now(UTC))
    _store().save(token)
    loaded = _store().load()
    assert loaded is not None
    assert not loaded.expires_within(120)
