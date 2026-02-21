from typing import Annotated

from fastapi import APIRouter, Response, Body
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_502_BAD_GATEWAY,
    HTTP_429_TOO_MANY_REQUESTS,
)

from ..dependencies import get_connection
from ..middlewares import AuthenticationMiddleware
from ..types import (
    Request,
    OTPVerifyBody,
    OTPRequestBody,
    OTPVerifyResponse,
    OTPRequestResponse,
)
from ...types import HTTPSerializedError
from ...services import errors
from ...services.database import AuthenticationRepository
from ...services.authentication import AuthenticationService

service = AuthenticationService(get_connection())
router = APIRouter(prefix="/authentication", tags=["authentication"])


@router.post(
    "/request-otp",
    summary="Requests a new OTP for the given phone number",
    response_description="The OTP expiry duration in seconds",
    responses={
        HTTP_429_TOO_MANY_REQUESTS: {
            "model": HTTPSerializedError,
            "content": {
                "application/json": {
                    "examples": {
                        "OTP rate limit exceeded": {
                            "value": {
                                "details": [
                                    errors.OTPRateLimitError(
                                        payload={"back_off": 60}
                                    ).serialize()
                                ]
                            }
                        },
                    }
                }
            },
        },
        HTTP_502_BAD_GATEWAY: {
            "model": HTTPSerializedError,
            "content": {
                "application/json": {
                    "examples": {
                        "Failed to send SMS": {
                            "value": {
                                "details": [
                                    errors.SMSSendError("09170000000").serialize()
                                ]
                            }
                        },
                    }
                }
            },
        },
    },
)
async def request_otp(body: OTPRequestBody) -> OTPRequestResponse:
    """Sends an OTP to the provided phone number."""
    return OTPRequestResponse(expires_in=(await service.request_otp(body.phone)))


@router.post(
    "/verify-otp",
    summary="Verifies the OTP and creates a session",
    response_description="The session token and its max age",
    responses={
        HTTP_400_BAD_REQUEST: {
            "model": HTTPSerializedError,
            "content": {
                "application/json": {
                    "examples": {
                        "invalid OTP code": {
                            "value": {
                                "details": [
                                    errors.OTPInvalidError(
                                        payload={
                                            "phone": "09170000000",
                                            "code": "1234",
                                        }
                                    ).serialize()
                                ]
                            }
                        },
                        "OTP has expired": {
                            "value": {
                                "details": [
                                    errors.OTPExpiredError(
                                        payload={
                                            "phone": "09170000000",
                                            "code": "1234",
                                        }
                                    ).serialize()
                                ]
                            }
                        },
                    }
                }
            },
        },
        HTTP_429_TOO_MANY_REQUESTS: {
            "model": HTTPSerializedError,
            "content": {
                "application/json": {
                    "examples": {
                        "maximum verification attempts exceeded": {
                            "value": {
                                "details": [
                                    errors.OTPMaxAttemptsError(
                                        payload={
                                            "phone": "09123456789",
                                            "code": "1234",
                                        }
                                    ).serialize()
                                ]
                            }
                        },
                    }
                }
            },
        },
    },
)
async def verify_otp(body: OTPVerifyBody, response: Response) -> OTPVerifyResponse:
    result = service.verify_otp(
        phone=body.phone, code=body.code, platform=body.platform
    )

    response.set_cookie(
        key="token",
        samesite="lax",
        secure=True,
        httponly=True,
        value=result["token"],
        max_age=result["max_age"],
    )

    return OTPVerifyResponse(token=result["token"], max_age=result["max_age"])


@router.post(
    "/verify-token",
    summary="Checks whether the given token belongs to an active session",
)
async def verify_token(
    request: Request,
    token: Annotated[
        str | None,
        Body(
            embed=True,
            description=(
                "The session token to verify. "
                "If omitted, the token is read from the Authorization header or cookie."
            ),
        ),
    ] = None,
) -> bool:
    token = token or AuthenticationMiddleware.get_token(request)
    if not token:
        return False

    return service.get_user(token) is not None


@router.post("/logout", summary="Logs out the current user by invalidating the session")
async def logout(request: Request, response: Response) -> "None":
    token = request.extract_token()
    with AuthenticationRepository(get_connection()) as repo:
        if repo.delete_session(service.hash_token(token)):
            response.delete_cookie("token")
