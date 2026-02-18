import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR

from .routes import authentication
from .dependencies import close_connection
from .middlewares import AuthenticationMiddleware
from .. import __version__
from ..config import config
from ..cleanup import Cleanup
from ..types import HTTPSerializedError
from ..errors import BaseError, UnexpectedError

logger = logging.getLogger(__name__)
app = FastAPI(
    middleware=[Middleware(AuthenticationMiddleware)],
    responses={
        HTTP_400_BAD_REQUEST: (model := {"model": HTTPSerializedError}),
        HTTP_500_INTERNAL_SERVER_ERROR: model,
    },
    default_response_class=ORJSONResponse,
    version=__version__,
    title="GramFood API",
    root_path="/",
    openapi_url="/openapi.json" if config["api"]["ui"] else None,
    docs_url="/api",
    redoc_url=None,
    swagger_ui_oauth2_redirect_url=None,
    swagger_ui_parameters={
        "filter": True,
        "tryItOutEnabled": True,
        "displayRequestDuration": True,
    },
)


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, BaseError):
        exc = UnexpectedError(cause=exc)

    return await http_exception_handler(
        request, HTTPException(exc.http_code, exc.serialize())
    )


class API:
    """
    The API server class that manages the
    FastAPI application and its lifecycle.
    """

    __initiated = False

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._server: uvicorn.Server | None = None

        if not API.__initiated:
            app.router.lifespan_context = self._lifespan
            app.include_router(authentication.router)

            self._server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    port=443,
                    host="0.0.0.0",
                    log_config=None,  # Already configured
                    access_log=False,
                    reload=False,
                    date_header=False,
                    server_header=False,
                    backlog=2048,
                    timeout_keep_alive=15,
                    forwarded_allow_ips="*",
                    # uds=config["api"]["socket_path"],
                    timeout_graceful_shutdown=config["api"]["graceful_shutdown"],
                )
            )

            API.__initiated = True

    @staticmethod
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("The API server is started")

        # If `SIGINT` signal received before application startup,
        # `CancelledError` would be raised in here and prevents
        # the proper application shutdown.
        # See https://github.com/encode/uvicorn/discussions/1662
        with suppress(asyncio.CancelledError):
            yield

        close_connection()
        logger.info("The API server is stopped")

    def start(self) -> asyncio.Task:
        """Starts the server.

        Returns:
            The related AsyncIO Task that can be awaited on.

        Raises:
            `RuntimeError`:
                When called while the procedure is already running.
        """
        if self._task is not None:
            raise RuntimeError("Server is already running")

        Cleanup.add(self.stop)
        self._task = asyncio.create_task(self._server.serve(), name="api")
        return self._task

    async def stop(self) -> None:
        """Stops the server."""
        if self._task:
            if self._server and not self._task.done():
                self._server.should_exit = True
                await self._task

            self._task = None
            self._server = None
            API.__initiated = False
