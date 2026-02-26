from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from ...utils import normalize_phone
from ...services.constants import Platform
from ...services.packages.constants import MealType

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


class CreatePackageBody(BaseModel):
    name: Annotated[str, Field(description="The unique package name.")]
    price: Annotated[float, Field(description="The package price.", gt=0)]


class CreatePackageResponse(BaseModel):
    id: Annotated[int, Field(description="The created package ID.")]


class UpdatePackageBody(BaseModel):
    name: Annotated[
        str | None, Field(default=None, description="The new package name.")
    ]
    price: Annotated[
        float | None, Field(default=None, description="The new package price.", gt=0)
    ]
    is_enabled: Annotated[
        bool | None,
        Field(default=None, description="Whether the package is enabled."),
    ]


class SubscribeBody(BaseModel):
    package_id: Annotated[int, Field(description="The package ID to subscribe to.")]
    meal_type: Annotated[MealType, Field(description="The meal type selection.")]
    diet_drink: Annotated[
        bool, Field(default=False, description="Whether to include a diet drink.")
    ]
    allergies: Annotated[
        list[Annotated[str, Field(max_length=100)]] | None,
        Field(
            default=None,
            max_length=50,
            description="List of ingredients the user is allergic to (max 50 items, each max 100 chars).",
        ),
    ]
    num_weeks: Annotated[
        int,
        Field(description="Number of weeks for the subscription (1-4).", ge=1, le=4),
    ]


class SubscribeResponse(BaseModel):
    id: Annotated[int, Field(description="The subscription record ID.")]
    start_date: Annotated[str, Field(description="The Jalali start date.")]
    end_date: Annotated[str, Field(description="The Jalali end date.")]
