import json
import sqlite3
import logging
from datetime import datetime

from .constants import MealType
from .types import Package, UserPackage
from .errors import DuplicatePackageNameError
from ...database import BaseRepository

logger = logging.getLogger(__name__)


class PackageRepository(BaseRepository):
    """Repository managing packages catalog and user subscriptions."""

    def __init__(
        self, connection: sqlite3.Connection | None = None, *, atomic: bool = False
    ) -> None:
        super().__init__(connection, atomic=atomic)
        self._logger = logger.getChild(self.__class__.__name__)

    def schema(self) -> None:
        sqlite3.register_converter("MealType", lambda b: MealType(b.decode()))

        with self._connection:
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL,
                    is_enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now'))
                );
                """
            )
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS user_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    package_id INTEGER NOT NULL,
                    meal_type MealType NOT NULL,
                    diet_drink BOOLEAN DEFAULT 0,
                    allergies JSON DEFAULT NULL,
                    start_date DATETIME NOT NULL,
                    end_date DATETIME NOT NULL,
                    is_reserved BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT (strftime('{self._sqlite_date_format}','now')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE RESTRICT
                );
                """
            )

    # -- Package catalog methods --

    @BaseRepository.auto_commit
    def add_package(self, name: str, price: float) -> int:
        """Adds a new package to the catalog and returns its ID.

        Raises:
            ``DuplicatePackageNameError``:
                If a package with the given name already exists.
        """
        try:
            cursor = self._connection.execute(
                "INSERT INTO packages (name, price) VALUES (?, ?)",
                (name, price),
            )
        except sqlite3.IntegrityError:
            raise DuplicatePackageNameError(name)

        self._logger.debug(
            f"Package created | name={name} price={price} id={cursor.lastrowid}"
        )
        return cursor.lastrowid

    @BaseRepository.auto_commit
    def update_package(
        self,
        package_id: int,
        *,
        name: str | None = None,
        price: float | None = None,
        is_enabled: bool | None = None,
    ) -> bool:
        """Updates a package's fields. Returns `True` if upgraded.

        Raises:
            ``DuplicatePackageNameError``:
                If the new name conflicts with an existing package.
        """
        fields: list[str] = []
        params: list = []

        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if price is not None:
            fields.append("price = ?")
            params.append(price)
        if is_enabled is not None:
            fields.append("is_enabled = ?")
            params.append(is_enabled)

        if not fields:
            return False

        params.append(package_id)
        try:
            cursor = self._connection.execute(
                f"UPDATE packages SET {', '.join(fields)} WHERE id = ?",
                params,
            )
        except sqlite3.IntegrityError:
            raise DuplicatePackageNameError(name)

        if cursor.rowcount > 0:
            self._logger.debug(f"Package updated | id={package_id}")
            return True
        return False

    def get_package_by_id(self, package_id: int) -> Package | None:
        """Returns a package by its ID."""
        return self._connection.execute(
            "SELECT * FROM packages WHERE id = ?",
            (package_id,),
        ).fetchone()

    def get_enabled_packages(self) -> list[Package]:
        """Returns all enabled packages."""
        return self._connection.execute(
            "SELECT * FROM packages WHERE is_enabled = 1 ORDER BY id"
        ).fetchall()

    def get_all_packages(self) -> list[Package]:
        """Returns all packages regardless of status."""
        return self._connection.execute("SELECT * FROM packages ORDER BY id").fetchall()

    # -- User subscription methods --

    @BaseRepository.auto_commit
    def add_user_package(
        self,
        *,
        user_id: int,
        package_id: int,
        meal_type: MealType,
        diet_drink: bool,
        allergies: list | None,
        start_date: datetime,
        end_date: datetime,
        is_reserved: bool = False,
    ) -> int:
        """Adds a user package subscription and returns the record ID."""
        cursor = self._connection.execute(
            """
            INSERT INTO user_packages (
                user_id, package_id, meal_type, diet_drink,
                allergies, start_date, end_date, is_reserved
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                package_id,
                meal_type,
                diet_drink,
                json.dumps(allergies) if allergies is not None else None,
                start_date,
                end_date,
                is_reserved,
            ),
        )

        self._logger.debug(
            f"User package added | "
            f"user_id={user_id} package_id={package_id} is_reserved={is_reserved}"
        )
        return cursor.lastrowid

    def get_active_subscription(self, user_id: int) -> UserPackage | None:
        """Returns the active (non-reserved) subscription for the user if exists."""
        return self._connection.execute(
            f"""
            SELECT * FROM user_packages
            WHERE user_id = ? AND is_reserved = 0
                AND start_date <= strftime('{self._sqlite_date_format}', 'now')
                AND end_date >= strftime('{self._sqlite_date_format}', 'now')
            ORDER BY start_date DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    def get_reserved_subscription(self, user_id: int) -> UserPackage | None:
        """Returns the reserved subscription for the user if exists."""
        return self._connection.execute(
            f"""
            SELECT * FROM user_packages
            WHERE user_id = ? AND is_reserved = 1
                AND end_date >= strftime('{self._sqlite_date_format}', 'now')
            ORDER BY start_date DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    def get_user_subscriptions(self, user_id: int) -> list[UserPackage]:
        """Returns all subscriptions for a given user."""
        return self._connection.execute(
            """
            SELECT up.*, p.name as package_name, p.price as package_price
            FROM user_packages up
            JOIN packages p ON up.package_id = p.id
            WHERE up.user_id = ?
            ORDER BY up.start_date DESC
            """,
            (user_id,),
        ).fetchall()

    def get_subscriptions_in_range(
        self, start_date: datetime, end_date: datetime
    ) -> list[UserPackage]:
        """Returns all subscriptions overlapping with the given date range.

        Used by operators to view upcoming meal preparation schedule.
        """
        return self._connection.execute(
            """
            SELECT up.*, p.name as package_name, p.price as package_price,
                   u.phone as user_phone, u.name as user_name
            FROM user_packages up
            JOIN packages p ON up.package_id = p.id
            JOIN users u ON up.user_id = u.id
            WHERE up.start_date <= ? AND up.end_date >= ?
            ORDER BY up.start_date ASC
            """,
            (end_date, start_date),
        ).fetchall()

    @BaseRepository.auto_commit
    def activate_reserved_subscription(self, user_id: int) -> bool:
        """Activates the reserved subscription by clearing the reserved flag.

        Returns `True` if a subscription was activated.
        """
        cursor = self._connection.execute(
            """
            UPDATE user_packages
            SET is_reserved = 0
            WHERE user_id = ? AND is_reserved = 1
            ORDER BY start_date ASC
            LIMIT 1
            """,
            (user_id,),
        )

        if cursor.rowcount > 0:
            self._logger.debug(f"Reserved subscription activated | user_id={user_id}")
            return True
        return False
