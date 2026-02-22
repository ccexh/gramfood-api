from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from ...utils import normalize_phone
from ...services.constants import Platform

type NormalizedPhone = Annotated[str, AfterValidator(normalize_phone)]


class OTPRequestBody(BaseModel):
    phone: Annotated[NormalizedPhone, Field(description="The user's phone number.")]


class OTPRequestResponse(BaseModel):
    expires_in: Annotated[int, Field(description="The OTP expiry duration in seconds.")]


class OTPVerifyBody(BaseModel):
    phone: Annotated[NormalizedPhone, Field(description="The user's phone number.")]
    code: Annotated[str, Field(description="The OTP code to verify.")]
    platform: Annotated[
        Platform,
        Field(description="The platform of the device initiating the verification."),
    ]


class OTPVerifyResponse(BaseModel):
    token: Annotated[str, Field(description="The session token.")]
    max_age: Annotated[int, Field(description="The session token max age in seconds.")]


class VerifyTokenBody(BaseModel):
    token: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "The session token to verify. "
                "If omitted, the token is read from the Authorization header or cookie."
            ),
        ),
    ]
