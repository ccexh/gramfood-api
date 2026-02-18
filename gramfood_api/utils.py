import os
import math
import re
import fcntl
import asyncio
from typing import Any
from pathlib import Path
from datetime import datetime, timezone
from collections.abc import Iterable

import uvloop

from .config import config
from .cleanup import Cleanup
from .types import DataUnits
from .log import uncaught_exception_handler


def create_event_loop() -> uvloop.Loop:
    """Creates the AsyncIO event loop."""
    loop = uvloop.new_event_loop()
    loop.set_exception_handler(uncaught_exception_handler)
    asyncio.set_event_loop(loop)

    return loop


def is_duplicated_instance() -> bool:
    """Whether there are other running instance of the application."""
    lock_path = Path(config["main"]["temp_path"]).joinpath(".lock")
    lock = os.open(lock_path, os.O_WRONLY | os.O_CREAT)

    try:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        Cleanup.add(
            # Gracefully unlock and remove the lock file
            lambda: (
                fcntl.lockf(lock, fcntl.LOCK_UN) is None
                and lock_path.unlink(missing_ok=True)
            )
        )
        return False
    except IOError:
        return True


def convert_size(
    size: int,
    precision: int = 2,
    *,
    separator: str = "",
    units: DataUnits | None = None,
) -> str:
    """Approximately converts the input value in bytes to a bigger decimal unit prefix.

    Args:
        `separator`: The unit separator character.
        `units`: The map of the data unit abbreviations to custom names.
    """
    prefixes = ("B", "kB", "MB", "GB", "TB", "PB")
    if size == 0:
        return f"0{separator}{units['B'] if units else prefixes[0]}"

    magnitude = int(math.floor(math.log(size, 1000)))
    unit = prefixes[magnitude]
    return "".join(
        (
            str(round(size / math.pow(1000, magnitude), precision or None)),
            separator,
            units[unit] if units else unit,
        )
    )


def current_time() -> datetime:
    """Returns the current time in the UTC timezone."""
    return datetime.now(timezone.utc)


def normalize_phone(value: str | int) -> str | None:
    """
    Returns the normalized Iranian phone number that
    starts with zero and has stripped country code.

    Returns `None` for invalid input.
    """
    match = re.match(r"^((\+98)|0)?(9[\d]{9})$", str(value))
    return f"0{match.group(3)}" if match else None


async def gather(iterable: Iterable) -> tuple[list[Any], list[Exception]]:
    """
    Wrapper around ``asyncio.gather()`` that
    separates the exceptions from the results.
    """
    returns = []
    exceptions = []
    for result in await asyncio.gather(*iterable, return_exceptions=True):
        (exceptions if isinstance(result, Exception) else returns).append(result)

    return (returns, exceptions)
