import json
import asyncio
import logging
import sqlite3
import functools
from os import PathLike
from typing import Self
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from collections.abc import Callable

from .config import config
from .cleanup import Cleanup
from .types import DatabaseSchema
from .utils import current_time, convert_size

database_dir = Path(config["database"]["path"])
database_path = database_dir.joinpath("index.db")
backup_dir = database_path.with_name("backup")
logger = logging.getLogger(__name__)

if not database_dir.exists():
    database_dir.mkdir(parents=True, exist_ok=True)


class Database:
    """The interface to manage the database.

    Returns:
        The database connection object that can be used
        to interact with the database.
    """

    __slots__ = ("connection",)

    __backup_task = None

    def __new__(cls) -> sqlite3.Connection:
        database = super().__new__(cls)
        database.__init__()
        return database.connection

    def __init__(self) -> None:
        self.connection = sqlite3.connect(
            database_path,
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self.connection.row_factory = sqlite3.Row

        # It's not possible to enable the following pragmas within a transaction
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")

    @staticmethod
    def size(connection: sqlite3.Connection) -> int:
        """Returns the database size in bytes."""
        result = connection.execute(
            """
            SELECT page_count * page_size as size
            FROM pragma_page_count(), pragma_page_size()
            """
        ).fetchone()

        return result["size" if type(result) is dict else 0]

    @classmethod
    def dump(cls, path: PathLike | None = None) -> DatabaseSchema:
        """Returns the current state of the database as a dictionary.

        Args:
            `path`: The location to store the dumb file as `JSON`.
        """
        connection = cls()
        try:
            output = {
                table["name"]: [
                    dict(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table['name']}"
                    ).fetchall()
                ]
                for table in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()

        if path:
            with open(path, "w") as file:
                json.dump(output, file, indent=2)

        return output

    @classmethod
    def backup(cls, suffix: str | None = None) -> None:
        """Creates a backup of the database.

        Args:
            `suffix`:
                The backup file name suffix.
                If omitted, `%timestamp%` will be used.

        Raises:
            `FileExistsError`:
                When a backup file with the same name already exists.
        """
        if not suffix:
            suffix = f"{current_time().strftime(r'.%Y%m%d%H%M%S')}.bak"

        if not backup_dir.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)

        backup_name = f"{database_path.name}{suffix}"
        backup_path = backup_dir.joinpath(backup_name)
        if backup_path.exists():
            raise FileExistsError(f"Backup file '{backup_name}' already exists")

        with sqlite3.connect(
            backup_path,
            # It's not possible to perform `VACUUM`
            # command within a transaction
            autocommit=True,
        ) as db:
            # It seems `backup()` method (and then `VACUUM` command)
            # do not blocks the original database's transactions so
            # it's favored over `VACUUM INTO` command.
            _db = cls()
            _db.backup(db)
            _db.close()
            previous_size = cls.size(db)
            db.execute("VACUUM")
            reduced = previous_size - cls.size(db)

        db.close()
        logger.debug(
            f"The database backup file '{backup_name}' is created{
                f" (file size reduced by '{convert_size(reduced)}')"
                if reduced > 0
                else ''
            }"
        )

    @classmethod
    def remove_old_backups(cls) -> None:
        """Removes old backup files exceeding the maximum allowed number."""
        if (maximum_backups := config["database"]["maximum_backups"]) > 0:
            for backup_file in (
                sorted(
                    backup_dir.glob("*.bak"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )[maximum_backups:]:
                try:
                    backup_file.unlink()
                    logger.debug(f"Removed old backup file '{backup_file.name}'")
                except Exception:
                    logger.exception(
                        f"Failed to remove backup file '{backup_file.name}'"
                    )

    @classmethod
    def start_backup(cls) -> asyncio.Task | None:
        """Starts the database backup procedure.

        The backup interval can be configured with `backup_interval`
        property in the configuration file.

        Returns:
            The related AsyncIO Task that can be awaited on.

        Raises:
            ``RuntimeError``:
                When called while the procedure is already running.
        """
        if cls.__backup_task is not None:
            raise RuntimeError("The database backup procedure is already running")
        elif config["database"]["backup_interval"] <= 0:
            logger.debug("The database backup procedure is disabled")
            return

        async def _backup() -> None:
            logger.info("The database backup procedure is started")
            while True:
                backup_interval = config["database"]["backup_interval"]
                if backup_interval <= 0:
                    logger.debug("The database backup procedure is disabled")
                    break

                try:
                    await asyncio.sleep(backup_interval)
                    cls.backup()
                    cls.remove_old_backups()
                except asyncio.CancelledError:
                    logger.info("The database backup procedure is stopped")
                    raise

        Cleanup.add(cls.stop_backup)
        cls.__backup_task = asyncio.create_task(_backup(), name="database_backup")
        return cls.__backup_task

    @classmethod
    def stop_backup(cls) -> None:
        """Stops the database backup procedure."""
        if (task := cls.__backup_task) is not None and not task.done():
            task.cancel()
            cls.__backup_task = None


class BaseRepository(ABC):
    """The base repository to be inherited by other repositories.

    Args:
        `connection`:
            The database connection to use.
            If omitted, a new connection will be created.
        `atomic`:
            If `True`, the entire `with` block is executed inside
            a single transaction. Outside a context manager, write
            methods still auto-commit individually.
    """

    __types_registered = False
    __initialized_repos: set[type] = set()

    def __init__(
        self, connection: sqlite3.Connection | None = None, *, atomic: bool = False
    ) -> None:
        self._connection = connection or Database()
        self._atomic = atomic

        self._is_transaction_started = False
        self._is_internal_connection = connection is None

        # SQLite's `%f` means `SS.SSS` (seconds with 3 decimal places),
        # unlike Python's `%f` which means microseconds only.
        self._date_format = "%Y-%m-%d %H:%M:%S.%f"
        self._sqlite_date_format = "%Y-%m-%d %H:%M:%f"

        self._ensure_schema()

    def __enter__(self):
        if self._atomic and not self._connection.in_transaction:
            self._connection.execute("BEGIN")
            self._is_transaction_started = True

        return self

    def __exit__(self, exc_type, exc, tb):
        if self._is_transaction_started:
            if exc_type is None:
                try:
                    self._connection.commit()
                except Exception:
                    self._connection.rollback()
                    raise
            else:
                self._connection.rollback()

        self.close()

    def _ensure_schema(self) -> None:
        if not BaseRepository.__types_registered:
            sqlite3.register_adapter(bool, lambda b: 1 if b else 0)
            sqlite3.register_converter("BOOLEAN", lambda b: bool(int(b)))
            sqlite3.register_adapter(
                datetime, lambda dt: dt.strftime(self._date_format)
            )
            sqlite3.register_converter(
                "DATETIME",
                lambda b: datetime.fromisoformat(b.decode()).replace(
                    tzinfo=timezone.utc
                ),
            )
            BaseRepository.__types_registered = True

        if (cls := self.__class__) not in (repos := BaseRepository.__initialized_repos):
            self.schema()
            repos.add(cls)

    @abstractmethod
    def schema(self) -> None:
        """Defines the database schema for the repository.

        This method should be overridden by derived classes to create
        the necessary tables and custom types.
        """
        raise NotImplementedError()

    @staticmethod
    def auto_commit[**P, R](method: Callable[P, R]) -> Callable[P, R]:
        """Add implicit commit handling for write operations.

        If a transaction is already active on the connection, the wrapped
        method executes directly. Otherwise it is executed inside an implicit
        transaction block using the connection context manager.
        """

        @functools.wraps(method)
        def wrapper(self: Self, *args: P.args, **kwargs: P.kwargs) -> R:
            if self._connection.in_transaction:
                return method(self, *args, **kwargs)
            with self._connection:
                return method(self, *args, **kwargs)

        return wrapper

    def close(self) -> None:
        if self._is_internal_connection and self._connection:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection
