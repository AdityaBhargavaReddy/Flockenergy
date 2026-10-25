"""Exceptions for Upstream Urja Meter Ops Portal client."""


class UrjaPortalError(Exception):
    """Base exception for all portal communication failures."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UrjaAuthenticationError(UrjaPortalError):
    """Raised when authentication with the Urja portal fails."""

    def __init__(self, message: str = "Failed to authenticate with upstream Urja portal"):
        super().__init__(message, status_code=502)


class UrjaNotFoundError(UrjaPortalError):
    """Raised when a meter or requested entity does not exist upstream."""

    def __init__(self, message: str = "Resource not found on upstream portal"):
        super().__init__(message, status_code=404)


class UrjaUpstreamError(UrjaPortalError):
    """Raised when upstream portal returns an unhandled error or times out."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code=status_code)
