from __future__ import annotations

import keyring

from schwab_dashboard.application.ports.tokens import OAuthTokenSet


class KeyringTokenStore:
    def __init__(self, *, service_name: str, account_name: str) -> None:
        self._service_name = service_name
        self._account_name = account_name

    def load(self) -> OAuthTokenSet | None:
        serialized = keyring.get_password(self._service_name, self._account_name)
        if serialized is None:
            return None
        return OAuthTokenSet.model_validate_json(serialized)

    def save(self, token: OAuthTokenSet) -> None:
        keyring.set_password(
            self._service_name,
            self._account_name,
            token.model_dump_json(),
        )

    def delete(self) -> None:
        try:
            keyring.delete_password(self._service_name, self._account_name)
        except keyring.errors.PasswordDeleteError:
            return
