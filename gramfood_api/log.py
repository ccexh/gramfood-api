import os
import sys
import threading
import logging
import logging.config
from copy import copy
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Literal, ClassVar

import click

from .config import config


class _ColourizedFormatter(logging.Formatter):
    """Custom log formatter to colorize the log levels."""

    level_name_colors = {
        logging.DEBUG: lambda level_name: click.style(str(level_name), fg="cyan"),
        logging.INFO: lambda level_name: click.style(str(level_name), fg="green"),
        logging.WARNING: lambda level_name: click.style(str(level_name), fg="yellow"),
        logging.ERROR: lambda level_name: click.style(str(level_name), fg="red"),
        logging.CRITICAL: lambda level_name: click.style(
            str(level_name), fg="bright_red"
        ),
    }

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        use_colors: bool | None = None,
    ) -> None:
        self.use_colors = use_colors if use_colors is not None else sys.stdout.isatty()
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def color_level_name(self, level_name: str, level_no: int) -> str:
        return self.level_name_colors.get(level_no, lambda level_name: str(level_name))(
            level_name
        )

    def formatMessage(self, record: logging.LogRecord) -> str:
        _record = copy(record)
        level_name = (
            self.color_level_name(_record.levelname, _record.levelno)
            if self.use_colors
            else _record.levelname
        )
        separator = " " * (8 - len(_record.levelname))
        _record.__dict__["levelprefix"] = f"{level_name}:{separator}"

        return super().formatMessage(_record)


class _StorageFormatter(logging.Formatter):
    """Custom log formatter to use UTC time standard and control the traceback."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._traceback = True

    def formatException(self, *args) -> str:
        return super().formatException(*args) if self._traceback else ""

    def converter(self, timestamp):
        return datetime.fromtimestamp(timestamp, tz=ZoneInfo("Asia/Tehran")).timetuple()


class _ConsoleFormatter(_ColourizedFormatter):
    """Custom log formatter to control the traceback."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = logging.Formatter.default_time_format,
        trim_level: bool = True,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, *args, **kwargs)
        self._trim_level = trim_level

    def formatException(self, *args) -> str:
        return (
            super().formatException(*args) if config["log"]["console_traceback"] else ""
        )

    def formatMessage(self, record: logging.LogRecord) -> str:
        if self._trim_level:
            # Preventing the padding space to be added
            # to the log level by the inherited method
            levelname = record.levelname
            if self.use_colors:
                levelname = self.color_level_name(levelname, record.levelno)
                if "color_message" in record.__dict__:
                    record.msg = record.__dict__["color_message"]
                    record.__dict__["message"] = record.getMessage()

            record.__dict__["levelprefix"] = levelname
            return logging.Formatter.formatMessage(self, record)

        return super().formatMessage(record)


class LogManager:
    """The log manager that configures and manages logging."""

    __instance: ClassVar[LogManager | None] = None

    def __new__(cls) -> LogManager:
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __init__(self) -> None:
        if hasattr(self, "_config"):
            return

        config_log = config["log"]
        storage_size = abs(config_log["storage_size"])
        storage_log_level = logging.getLevelName(config_log["storage_level"].upper())
        console_log_level = logging.getLevelName(config_log["console_level"].upper())
        self._log_dir = Path(config_log["path"])
        self._config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "()": _ConsoleFormatter,
                    "format": "%(asctime)s [%(levelprefix)s] [%(name)s] %(message)s",
                },
                "storage": {
                    "()": _StorageFormatter,
                    "format": "%(asctime)s | %(process)d | %(levelname)s | %(name)s --> %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "level": console_log_level,
                    "stream": "ext://sys.stdout",
                },
                f"storage_{__package__}": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "storage",
                    "level": storage_log_level,
                    "filename": self._log_dir.joinpath(f"{__package__}.log"),
                    "mode": "a+",
                    "maxBytes": 1048576,
                    "backupCount": storage_size,
                },
                "storage_uvicorn": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "storage",
                    "level": storage_log_level,
                    "filename": self._log_dir.joinpath("uvicorn.log"),
                    "mode": "a+",
                    "maxBytes": 1048576,
                    "backupCount": storage_size,
                },
                "storage_uvicorn_access": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "storage",
                    "level": storage_log_level,
                    "filename": self._log_dir.joinpath("uvicorn-access.log"),
                    "mode": "a+",
                    "maxBytes": 1048576,
                    "backupCount": storage_size,
                },
            },
            "loggers": {
                __package__: {
                    "handlers": ["console", f"storage_{__package__}"],
                    "level": logging.DEBUG,
                },
                "uvicorn.error": {
                    "handlers": ["storage_uvicorn"],
                    "level": logging.DEBUG,
                },
                "uvicorn.access": {
                    "handlers": ["storage_uvicorn_access"],
                    "level": logging.DEBUG,
                },
            },
        }

        self._setup()

    def _setup(self) -> None:
        """Configures the logger."""
        if config["log"]["store"]:
            if not self._log_dir.exists():
                self._log_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Preventing the logs to be stored on the disk
            for handler in list(self._config["handlers"].keys()):
                if handler.startswith("storage"):
                    del self._config["handlers"][handler]
            for logger in self._config["loggers"].values():
                for handler in (handlers := logger["handlers"]):
                    if handler.startswith("storage"):
                        handlers.remove(handler)

        # Attaching custom exception handler for logging the
        # uncaught exceptions in the main and derived threads.
        # NOTE: Handler also should be attached on AsyncIO's event
        #       loop on it's creation for handling uncaught exceptions
        #       in asynchronous tasks.
        sys.excepthook = threading.excepthook = uncaught_exception_handler
        logging.config.dictConfig(self._config)


def uncaught_exception_handler(*args) -> None:
    """Logs the unhandled exceptions."""
    logger = logging.getLogger(__package__)
    exc_type = exc_value = exc_traceback = None
    if len(args) == 1:
        # When passed to the `threading.excepthook`
        exc_type = args[0].exc_type
        exc_value = args[0].exc_value
        exc_traceback = args[0].exc_traceback
    elif len(args) == 2:
        # When passed to the `asyncio.loop.set_exception_handler`
        exc = args[1].get("exception", args[1]["message"])
        exc_type = exc.__class__
        exc_value = exc
        exc_traceback = exc.__traceback__
    elif len(args) == 3:
        # When passed to the `sys.excepthook`
        exc_type, exc_value, exc_traceback = args

    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        # Avoiding traceback on `KeyboardInterrupt` and `SystemExit`.
        # To show the traceback, next line could be uncommented.
        # sys.__excepthook__(exc_type, exc_value, exc_traceback)
        if isinstance(exc_value, SystemExit) and exc_value.code == os.EX_OK:
            return
        logger.warning("Application arbitrary killed by the user")
    else:
        logger.critical(exc_value, exc_info=(exc_type, exc_value, exc_traceback))
