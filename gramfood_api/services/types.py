from typing import TypedDict, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .constants import Platform


class OTP(TypedDict):
    id: int
    phone: str
    code: str
    expires_at: datetime
    attempts: int
    verified: bool
    created_at: datetime


class User(TypedDict):
    id: int
    phone: str
    name: str | None
    created_at: datetime
    updated_at: datetime


class Session(TypedDict):
    id: int
    user_id: int
    token: str
    platform: Platform
    expires_at: datetime
    created_at: datetime


class VerifyOTPResult(TypedDict):
    user: User
    token: str
    max_age: int
