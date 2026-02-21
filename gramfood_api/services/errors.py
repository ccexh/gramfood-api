from httpx import codes

from ..errors import BaseError


class SMSSendError(BaseError):
    """Failed to send an SMS message via the provider."""

    def __init__(self, phone: str, **kwargs) -> None:
        super().__init__(
            f"Failed to send an SMS message to '{phone}' via the provider.",
            1000,
            http_code=codes.BAD_GATEWAY,
            expose_payload=False,
            **kwargs,
        )


class DuplicateUserError(Exception):
    """User with the given phone number already exists."""

    def __init__(self, phone: str, **kwargs) -> None:
        super().__init__(
            f"User with phone '{phone}' already exists.",
            1001,
            http_code=codes.BAD_REQUEST,
            **kwargs,
        )


class OTPRateLimitError(BaseError):
    """OTP request rate limit is exceeded."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "OTP rate limit exceeded", 1002, http_code=codes.TOO_MANY_REQUESTS, **kwargs
        )


class OTPMaxAttemptsError(BaseError):
    """OTP maximum verification attempts exceeded."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "OTP maximum verification attempts exceeded",
            1003,
            http_code=codes.TOO_MANY_REQUESTS,
            **kwargs,
        )


class OTPExpiredError(BaseError):
    """OTP has expired."""

    def __init__(self, **kwargs) -> None:
        super().__init__("OTP has expired", 1004, http_code=codes.BAD_REQUEST, **kwargs)


class OTPInvalidError(BaseError):
    """OTP is invalid."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "Invalid OTP code", 1005, http_code=codes.BAD_REQUEST, **kwargs
        )
