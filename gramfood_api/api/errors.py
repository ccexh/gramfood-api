from httpx import codes

from ..errors import BaseError


class NotAuthenticatedError(BaseError):
    """User is not authenticated."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Not authenticated", 2000, http_code=codes.UNAUTHORIZED, **kwargs
        )


class InvalidSessionError(BaseError):
    """Session is invalid or expired."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Invalid or expired session", 2001, http_code=codes.UNAUTHORIZED, **kwargs
        )
