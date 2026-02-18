import os
import sys
import time
import asyncio
import logging
import inspect
import multiprocessing
from typing import ClassVar, Final
from signal import Signals, SIGINT, SIGTERM, SIGHUP, SIGQUIT
from collections.abc import Callable

DEBOUNCE_DURATION: Final[float] = 0.25  # seconds

logger = logging.getLogger(__name__)


class Cleanup:
    """
    Clean up handler that runs registered tasks on application
    termination by the `SIGINT` or `SIGTERM` signals.
    """

    __pid: ClassVar[int | None] = None
    __instance: ClassVar[Cleanup | None] = None
    __callbacks: ClassVar[set[Callable]] = set()

    _last_termination_signal_at: float | None
    _is_cleaning: bool | None
    _is_terminating: bool
    _is_restarting: bool
    _debounce_duration: float
    _process_name: str
    _is_main_process: bool
    _log: bool

    def __new__(cls) -> Cleanup:
        process = multiprocessing.current_process()
        if (pid := cls.__pid) != process.pid:
            cls.__pid = process.pid
            if pid is not None and len(cls.__callbacks):
                # Parent processes forked this process.
                # Previous tasks should be ignored.
                cls.__callbacks.clear()

            cls.__instance = super().__new__(cls)
            cls.__instance._last_termination_signal_at = None
            cls.__instance._is_cleaning = None
            cls.__instance._is_terminating = False
            cls.__instance._is_restarting = False
            cls.__instance._debounce_duration = DEBOUNCE_DURATION
            cls.__instance._process_name = process.name
            cls.__instance._is_main_process = process.name == "MainProcess"
            cls.__instance._log = (
                # Preventing duplicated logs on subprocesses
                cls.__instance._is_main_process
            )
            cls.__instance._listen()

        return cls.__instance

    async def _run_cleanup_tasks(self, signal: Signals) -> None:
        """Executes the cleanup tasks."""
        self._is_cleaning = True

        callbacks: list[Callable] = []
        async_callbacks: list[Callable] = []
        for callback in self.__callbacks:
            (
                async_callbacks
                if inspect.iscoroutinefunction(callback)
                or inspect.isawaitable(callback)
                else callbacks
            ).append(callback)

        if callbacks or async_callbacks:
            if self._log:
                message = "Waiting for the scheduled tasks to finish"
                if signal == SIGINT:
                    message += " (Ctrl+C to skip)"
                logger.info(message)

            # Waiting for the child processes to terminate
            if self._is_main_process:
                processes: list[multiprocessing.Process] = []
                for process in multiprocessing.active_children():
                    if process.name.startswith(__package__) and process.is_alive():
                        processes.append(process)
                        # The `SIGINT` signals initiated with Ctrl+C from the
                        # terminal will be propagated to all the child processes
                        # by default. The `SIGTERM` signal should be propagated.
                        if signal != SIGINT:
                            os.kill(process.pid, signal)

                for process in processes:
                    if process.is_alive():
                        process.join()

            if callbacks:
                for callback in callbacks:
                    callback()
            if async_callbacks:
                await asyncio.shield(
                    asyncio.gather(
                        *[callback() for callback in async_callbacks],
                        return_exceptions=True,
                    )
                )

            logger.debug(
                f"The scheduled tasks are finished successfully{
                    '' if self._is_main_process else f" (in '{self._process_name}')"
                }"
            )

            self._is_cleaning = False

    async def _termination_handler(self, signal: Signals) -> None:
        """Handles the clean up tasks on `SIGINT` or `SIGTERM` signal."""
        if self._is_restarting:
            logger.warning(f"Signal '{signal.name}' is ignored due to ongoing clean up")
            return

        now = time.monotonic()
        logger.debug(f"Signal '{signal.name}' is received, starting clean up...")

        if self._is_cleaning is None:
            self._last_termination_signal_at = now
            self._is_terminating = True
            await self._run_cleanup_tasks(signal)
            self._is_terminating = False
        # Ignore quick re-entrance
        elif now - self._last_termination_signal_at > self._debounce_duration:
            self._last_termination_signal_at = now
            if self._log and self._is_cleaning is True:
                logger.warning("The pending tasks are cancelled")

            self._is_terminating = False
            if self._is_main_process:
                sys.exit(signal)
            os._exit(signal)

    async def _restart_handler(self, signal: Signals) -> None:
        """Handles restart request on `SIGHUP` or `SIGQUIT` signal."""
        if self._is_main_process and not self._is_restarting:
            if self._is_terminating:
                logger.warning(
                    f"Signal '{signal.name}' is ignored due to ongoing clean up"
                )
                return

            logger.info(f"Signal '{signal.name}' is received, restarting...")
            if self._is_cleaning is None:
                self._is_restarting = True
                try:
                    await self._run_cleanup_tasks(SIGTERM)

                    # Re-executing the current process
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                finally:
                    self._is_restarting = False

    def _listen(self) -> None:
        """Attaches the signal handlers."""

        # Due to an unknown reason, storing the event loop inside a variable and
        # access it inside a for-loop will override the previous signal handlers!
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(
            SIGINT, lambda: asyncio.create_task(self._termination_handler(SIGINT))
        )
        loop.add_signal_handler(
            SIGTERM, lambda: asyncio.create_task(self._termination_handler(SIGTERM))
        )
        loop.add_signal_handler(
            SIGHUP, lambda: asyncio.create_task(self._restart_handler(SIGHUP))
        )
        loop.add_signal_handler(
            SIGQUIT, lambda: asyncio.create_task(self._restart_handler(SIGQUIT))
        )

    @classmethod
    def add(cls, callback: Callable) -> None:
        """Adds a callback function to the scheduled tasks."""
        cls.__callbacks.add(callback)

    @classmethod
    def remove(cls, callback: Callable) -> None:
        """Removes a callback function from the scheduled tasks."""
        try:
            cls.__callbacks.remove(callback)
        except KeyError:
            pass

    @property
    def is_cleaning(self) -> bool:
        """The clean up process running status at the current time."""
        return bool(self._is_cleaning)

    @property
    def log(self) -> bool:
        """The log status.

        By default, it's equal to `False` if this is not the main process.
        The value could be modified. However, that leads to duplicated logs
        if the clean up handler is running in multiple processes.
        """
        return self._log

    @log.setter
    def log(self, value: bool) -> None:
        self._log = value
