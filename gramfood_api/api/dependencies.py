import sqlite3

from ..database import Database

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Returns a shared database connection."""
    global _connection

    if _connection is None:
        _connection = Database()
    return _connection


def close_connection() -> None:
    """Closes the shared database connection."""
    global _connection

    if _connection is not None:
        _connection.close()
        _connection = None
