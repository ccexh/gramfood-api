from httpx import codes

from ..errors import BaseError


class ValidationError(BaseError):
    """Validation error for request or response data."""

    def __init__(self, message: str = "Validation error", **kwargs) -> None:
        super().__init__(message, 2000, http_code=codes.UNPROCESSABLE_ENTITY, **kwargs)


class NotAuthenticatedError(BaseError):
    """User is not authenticated."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Not authenticated", 2001, http_code=codes.UNAUTHORIZED, **kwargs
        )


class InvalidSessionError(BaseError):
    """Session is invalid or expired."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Invalid or expired session", 2002, http_code=codes.UNAUTHORIZED, **kwargs
        )
