class AuthenticationRequiredError(RuntimeError):
    """Raised when Schwab authorization is missing or can no longer be refreshed."""


class BrokerPayloadError(RuntimeError):
    """Raised when a required Schwab response shape cannot be mapped safely."""


class SyncValidationError(RuntimeError):
    """Raised when a broker observation cannot produce an unambiguous snapshot."""
