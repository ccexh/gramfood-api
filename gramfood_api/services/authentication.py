import hmac
import hashlib
import logging
import secrets
import sqlite3
from datetime import timedelta
from contextlib import suppress

from .constants import Platform
from .sms import SMSProviderClient
from .types import User, VerifyOTPResult
from .database import AuthenticationRepository
from .errors import (
    SMSSendError,
    OTPExpiredError,
    OTPInvalidError,
    OTPRateLimitError,
    OTPMaxAttemptsError,
    DuplicateUserError,
)
from ..config import config
from ..utils import current_time

logger = logging.getLogger(__name__)


class AuthenticationService:
    """Handles authentication business logic."""

    def __init__(self, connection: sqlite3.Connection | None = None) -> None:
        self._connection = connection
        self._sms = SMSProviderClient()

    @staticmethod
    def _hash_token(value: str) -> str:
        """Returns the HMAC-SHA-256 hex digest of the given value using a salt."""
        return hmac.new(
            config["authentication"]["token_hash_salt"].encode(),
            value.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def request_otp(self, phone: str) -> int:
        """Requests a new OTP for the given phone number.

        Returns:
            The OTP expiry duration in seconds.

        Raises:
            ``OTPRateLimitError``:
                If a recent OTP already exists for the phone,
                or the maximum number of OTP requests within the
                configured time window has been exceeded.
            ``SMSSendError``:
                If the SMS provider fails to send the OTP.
        """
        config_authentication = config["authentication"]
        otp_expiry = config_authentication["otp_expiry"]
        now = current_time()

        with AuthenticationRepository(self._connection) as repo:
            # Preventing multiple OTP requests when one is already valid
            latest_otp = repo.get_latest_otp(phone)
            if latest_otp is not None and latest_otp["expires_at"] > now:
                if (
                    remaining := int((latest_otp["expires_at"] - now).total_seconds())
                ) > otp_expiry / 2:
                    raise OTPRateLimitError(payload={"back_off": remaining})

            # Enforcing max OTP requests within the configured time window
            max_requests = config_authentication["otp_rate_limit_max_requests"]
            window = config_authentication["otp_rate_limit_window"]
            counts = repo.get_otp_counts(
                phone, from_date=now - timedelta(seconds=window)
            )
            if counts >= max_requests:
                raise OTPRateLimitError(
                    payload={
                        "back_off": window
                        - int((now - latest_otp["created_at"]).total_seconds())
                    }
                )

            length = config_authentication["otp_length"]
            code = str(secrets.randbelow(10**length)).zfill(length)
            with suppress(DuplicateUserError):
                repo.add_user(phone)

            otp_id = repo.add_otp(
                phone, self._hash_token(code), now + timedelta(seconds=otp_expiry)
            )

            try:
                await self._sms.send_otp(phone, code)
            except SMSSendError as error:
                repo.delete_otp(otp_id)
                logger.warning(repr(error))
                raise

            logger.info(f"OTP request created | phone={phone} otp_id={otp_id}")
            return otp_expiry

    def verify_otp(self, phone: str, code: str, platform: Platform) -> VerifyOTPResult:
        """Verifies OTP and creates a user session.

        Raises:
            ``OTPInvalidError``:
                If no OTP exists or the code is wrong.
            ``OTPExpiredError``:
                If the OTP has expired.
            ``OTPMaxAttemptsError``:
                If the maximum number of verification attempts
                has been exceeded.
        """
        now = current_time()
        config_authentication = config["authentication"]
        max_attempts = config_authentication["otp_max_verify_attempts"]

        with AuthenticationRepository(self._connection) as repo:
            latest_otp = repo.get_latest_otp(phone)
            if latest_otp is None:
                raise OTPInvalidError(payload={"phone": phone, "code": code})
            elif latest_otp["attempts"] >= max_attempts:
                repo.mark_otp_verified(latest_otp["id"])
                raise OTPMaxAttemptsError(payload={"phone": phone, "code": code})

            repo.increment_otp_attempts(latest_otp["id"])

            if latest_otp["expires_at"] <= now:
                raise OTPExpiredError(payload={"phone": phone, "code": code})
            # Preventing timing attacks
            elif not secrets.compare_digest(latest_otp["code"], self._hash_token(code)):
                raise OTPInvalidError(payload={"phone": phone, "code": code})

            repo.mark_otp_verified(latest_otp["id"])
            user = repo.get_user_by_phone(phone)
            if user is None:
                # Creating the user
                user_id = repo.add_user(phone)
                user = repo.get_user_by_id(user_id)

            max_age = config_authentication[
                "kiosk_session_max_age"
                if platform == Platform.KIOSK
                else "default_session_max_age"
            ]

            token = secrets.token_urlsafe(32)
            repo.add_session(
                user_id=user["id"],
                platform=platform,
                token=self._hash_token(token),
                expires_at=now + timedelta(seconds=max_age),
            )

            logger.debug(
                f"OTP verified and session created | "
                f"user_id={user['id']} phone={phone} platform={platform}"
            )
            return VerifyOTPResult(user=dict(user), token=token, max_age=max_age)

    def get_user(self, token: str) -> User | None:
        """Returns the user associated with the given session token."""
        with AuthenticationRepository(self._connection) as repo:
            return repo.get_user_by_token(self._hash_token(token))
