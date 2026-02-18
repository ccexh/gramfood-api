import asyncio
import logging

from . import __version__
from . import utils
from .log import LogManager
from .cleanup import Cleanup
from .database import Database
from .config import ConfigManager
from .api.app import API

logger = logging.getLogger(__name__)


async def start() -> None:
    """Starts the app.

    Raises:
        `RuntimeError`:
            When another instance of the app is running.
    """
    ConfigManager()
    LogManager()
    Cleanup()

    if utils.is_duplicated_instance():
        raise RuntimeError(
            f"Only one instance of '{__package__}' should run at the same time"
        )

    logger.info(f"'{__package__}' v{__version__} is started")
    await asyncio.wait(filter(None, [Database.start_backup(), API().start()]))
