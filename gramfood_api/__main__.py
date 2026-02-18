import asyncio
from typing import NoReturn

from . import app
from . import utils


def run() -> NoReturn:
    """Runs the app."""
    asyncio.run(app.start(), loop_factory=utils.create_event_loop)


if __name__ == "__main__":
    run()
