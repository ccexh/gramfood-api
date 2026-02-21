import sqlite3
import logging
from datetime import datetime

from .types import OTP, User
from .constants import Platform
from .errors import DuplicateUserError
from ..database import BaseRepository

logger = logging.getLogger(__name__)


class AuthenticationRepository(BaseRepository):
    """Authentication repository managing users, OTP codes, and sessions."""

    def __init__(
        self, connection: sqlite3.Connection | None = None, *, atomic: bool = False
    ) -> None:
        super().__init__(connection, atomic=atomic)
        self._logger = logger.getChild(self.__class__.__name__)

    def schema(self) -> None:
        sqlite3.register_converter("Platform", lambda b: Platform(b.decode()))

        with self._connection:
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL UNIQUE,
                    name TEXT,
                    created_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now')),
                    updated_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now'))
                );
                """
            )
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    code TEXT NOT NULL,
                    expires_at DATETIME NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    verified BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now')),
                    FOREIGN KEY (phone) REFERENCES users(phone) ON DELETE CASCADE
                );
                """
            )
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    platform Platform NOT NULL,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )

    @BaseRepository.auto_commit
    def add_otp(self, phone: str, code: str, expires_at: datetime) -> int:
        """Adds a new OTP record and returns the OTP ID."""
        cursor = self._connection.execute(
            "INSERT INTO otp_codes (phone, code, expires_at) VALUES (?, ?, ?)",
            (phone, code, expires_at),
        )

        self._logger.debug(f"OTP record created | phone={phone}")
        return cursor.lastrowid

    @BaseRepository.auto_commit
    def delete_otp(self, otp_id: int) -> None:
        """Deletes an OTP record by its ID."""
        if (
            self._connection.execute("DELETE FROM otp_codes WHERE id = ?", (otp_id,))
        ).lastrowid > 0:
            self._logger.debug(f"OTP record deleted | id={otp_id}")

    def get_latest_otp(self, phone: str) -> OTP | None:
        """Returns the latest unverified OTP for a phone number."""
        return self._connection.execute(
            """
            SELECT * FROM otp_codes
            WHERE phone = ? AND verified = 0
            ORDER BY id DESC LIMIT 1
            """,
            (phone,),
        ).fetchone()

    def get_otp_counts(
        self,
        phone: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int:
        """Returns the number of OTP records.

        Args:
            `from_date`:
                Filter OTP records created on or after this date.
                If `None`, no lower bound is applied.
            `to_date`:
                Filter OTP records created on or before this date.
                If `None`, no upper bound is applied.
        """
        params = [phone]
        conditions: list[str] = []

        if from_date is not None:
            conditions.append("created_at >= ?")
            params.append(from_date.strftime(self._sqlite_date_format))
        if to_date is not None:
            conditions.append("created_at <= ?")
            params.append(to_date.strftime(self._sqlite_date_format))

        return self._connection.execute(
            f"""
            SELECT COUNT(*) FROM otp_codes
            WHERE phone = ? {("AND " + " AND ".join(conditions)) if conditions else ""}
            """,
            params,
        ).fetchone()[0]

    @BaseRepository.auto_commit
    def increment_otp_attempts(self, otp_id: int) -> None:
        """Increments the verification attempt counter for an OTP record."""
        self._connection.execute(
            "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?",
            (otp_id,),
        )

    @BaseRepository.auto_commit
    def mark_otp_verified(self, otp_id: int) -> None:
        """Marks an OTP record as verified."""
        self._connection.execute(
            "UPDATE otp_codes SET verified = 1 WHERE id = ?",
            (otp_id,),
        )

        self._logger.debug(f"OTP marked as verified | id={otp_id}")

    @BaseRepository.auto_commit
    def add_user(self, phone: str) -> int:
        """Adds a new user record and returns the user ID.

        Raises:
            ``DuplicateUserError``:
                If a user with the given phone number already exists.
        """
        try:
            cursor = self._connection.execute(
                "INSERT INTO users (phone) VALUES (?)", (phone,)
            )
        except sqlite3.IntegrityError:
            raise DuplicateUserError(phone)

        self._logger.debug(f"User created | phone={phone} id={cursor.lastrowid}")
        return cursor.lastrowid

    def get_user_by_id(self, user_id: int) -> User | None:
        """Returns a user by ID."""
        return self._connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    def get_user_by_phone(self, phone: str) -> User | None:
        """Returns a user by phone number."""
        return self._connection.execute(
            "SELECT * FROM users WHERE phone = ?", (phone,)
        ).fetchone()

    def get_user_by_token(self, token: str) -> User | None:
        """Returns a user by session token hash if the session is not expired."""
        return self._connection.execute(
            f"""
            SELECT * FROM users
            JOIN sessions ON users.id = sessions.user_id
            WHERE sessions.token = ?
                AND sessions.expires_at > strftime('{self._sqlite_date_format}','now')
            """,
            (token,),
        ).fetchone()

    @BaseRepository.auto_commit
    def add_session(
        self, *, user_id: int, token: str, platform: Platform, expires_at: datetime
    ) -> None:
        """Adds a new session record."""
        self._connection.execute(
            """
            INSERT INTO sessions (user_id, token, platform, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, token, platform, expires_at),
        )

        self._logger.debug(f"Session created | user_id={user_id}")

    @BaseRepository.auto_commit
    def delete_session(self, token: str) -> bool:
        """Deletes a session by its token.

        Returns:
            `True` if a session was deleted, `False` otherwise.
        """
        if (
            self._connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        ).rowcount > 0:
            self._logger.debug(f"Session deleted | token={token[:8]}...")
            return True

        return False

    @BaseRepository.auto_commit
    def cleanup_expired(self) -> tuple[int, int]:
        """Removes expired sessions and verified/expired OTP codes."""
        sessions = self._connection.execute(
            f"""
            DELETE FROM sessions
            WHERE expires_at <= strftime('{self._sqlite_date_format}','now')
            """
        ).rowcount
        otps = self._connection.execute(
            f"""
            DELETE FROM otp_codes
            WHERE expires_at <= strftime('{self._sqlite_date_format}','now') OR verified = 1
            """
        ).rowcount

        if sessions > 0 or otps > 0:
            self._logger.debug(
                f"Cleanup expired completed | session={sessions} otp={otps}"
            )
