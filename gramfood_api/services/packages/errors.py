from httpx import codes

from ...errors import BaseError


class PackageNotFoundError(BaseError):
    """The requested package does not exist."""

    def __init__(self, package_id: int, **kwargs) -> None:
        super().__init__(
            f"Package with id '{package_id}' not found.",
            3000,
            http_code=codes.NOT_FOUND,
            **kwargs,
        )


class PackageDisabledError(BaseError):
    """The requested package is not enabled."""

    def __init__(self, package_id: int, **kwargs) -> None:
        super().__init__(
            f"Package with id '{package_id}' is disabled.",
            3001,
            http_code=codes.BAD_REQUEST,
            **kwargs,
        )


class DuplicatePackageNameError(BaseError):
    """A package with the given name already exists."""

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(
            f"Package with name '{name}' already exists.",
            3002,
            http_code=codes.CONFLICT,
            **kwargs,
        )


class ActiveSubscriptionExistsError(BaseError):
    """The user already has an active subscription."""

    def __init__(self, user_id: int, **kwargs) -> None:
        super().__init__(
            f"User '{user_id}' already has an active subscription.",
            3003,
            http_code=codes.CONFLICT,
            **kwargs,
        )


class ReservedSubscriptionExistsError(BaseError):
    """The user already has a reserved subscription."""

    def __init__(self, user_id: int, **kwargs) -> None:
        super().__init__(
            f"User '{user_id}' already has a reserved subscription.",
            3004,
            http_code=codes.CONFLICT,
            **kwargs,
        )


class ActiveSubscriptionNotFoundError(BaseError):
    """The user has no active subscription to reserve against."""

    def __init__(self, user_id: int, **kwargs) -> None:
        super().__init__(
            f"User '{user_id}' has no active subscription.",
            3005,
            http_code=codes.BAD_REQUEST,
            **kwargs,
        )


class InvalidWeekSelectionError(BaseError):
    """The selected weeks are invalid."""

    def __init__(self, message: str = "Invalid week selection.", **kwargs) -> None:
        super().__init__(message, 3006, http_code=codes.BAD_REQUEST, **kwargs)


class InsufficientRoleError(BaseError):
    """The user does not have the required role."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Insufficient permissions for this operation.",
            3007,
            http_code=codes.FORBIDDEN,
            **kwargs,
        )
