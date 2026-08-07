from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class OAuthTokenSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    expires_in: int = Field(default=1800, ge=1)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    refresh_issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.expires_in)

    def expires_within(self, seconds: int) -> bool:
        return self.expires_at <= datetime.now(UTC) + timedelta(seconds=seconds)

    @classmethod
    def from_oauth_response(
        cls,
        payload: dict[str, Any],
        *,
        previous: OAuthTokenSet | None = None,
    ) -> OAuthTokenSet:
        now = datetime.now(UTC)
        merged = dict(payload)
        if previous is not None:
            merged.setdefault("refresh_token", previous.refresh_token)
            merged["refresh_issued_at"] = previous.refresh_issued_at
        else:
            merged["refresh_issued_at"] = now
        merged["issued_at"] = now
        return cls.model_validate(merged)


class TokenStore(Protocol):
    def load(self) -> OAuthTokenSet | None: ...

    def save(self, token: OAuthTokenSet) -> None: ...

    def delete(self) -> None: ...
