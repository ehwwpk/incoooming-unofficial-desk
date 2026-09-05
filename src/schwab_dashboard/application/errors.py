class AuthenticationRequiredError(RuntimeError):
    """Raised when Schwab authorization is missing or can no longer be refreshed."""


class CredentialStoreError(AuthenticationRequiredError):
    """A safe diagnostic for unavailable or unreadable operating-system token storage."""


class SyncInProgressError(RuntimeError):
    """Raised when a second full sync is requested while one is already running."""


class BrokerPayloadError(RuntimeError):
    """Raised when a required Schwab response shape cannot be mapped safely."""


class BrokerRequestError(RuntimeError):
    """Raised when a Schwab request fails without exposing its URL or identifiers."""


class SyncValidationError(RuntimeError):
    """Raised when a broker observation cannot produce an unambiguous snapshot."""


class SourceRecordConflictError(RuntimeError):
    """Raised when a stable source identity is reused for different immutable facts."""
