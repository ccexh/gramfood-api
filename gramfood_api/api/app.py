import asyncio
import logging
from typing import ClassVar
from contextlib import suppress, asynccontextmanager
from collections.abc import AsyncGenerator, Callable

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.status import (
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from starlette.middleware.cors import CORSMiddleware

from .types import JSONResponse
from .errors import ValidationError
from .dependencies import close_connection
from .routes import authentication, packages
from .middlewares import AuthenticationMiddleware
from .. import __version__
from ..config import config
from ..cleanup import Cleanup
from ..types import SerializedError
from ..errors import BaseError, UnexpectedError

logger = logging.getLogger(__name__)


class API:
    """The API server class that manages the FastAPI application and its lifecycle."""

    __initiated: ClassVar[bool] = False

    _original_openapi: ClassVar[Callable[[], dict] | None] = None
    app: ClassVar[FastAPI | None] = None

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._server: uvicorn.Server | None = None

        if not API.__initiated:
            self.app = FastAPI(
                middleware=[Middleware(AuthenticationMiddleware)],
                responses={
                    HTTP_422_UNPROCESSABLE_CONTENT: {
                        "model": ValidationError.openapi_model(),
                        "content": {
                            "application/json": {
                                "examples": {
                                    "Request validation failed": {
                                        "value": ValidationError(
                                            "Field required",
                                            payload={
                                                "fields": ["field1", "field2"],
                                                "input": None,
                                            },
                                        ).serialize()
                                    }
                                }
                            }
                        },
                    },
                    HTTP_500_INTERNAL_SERVER_ERROR: {
                        "model": BaseError.openapi_model()
                        | UnexpectedError.openapi_model()
                    },
                },
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

            if config["main"]["development"]:
                cors = ["*"]
                self.app.add_middleware(
                    CORSMiddleware,
                    allow_origins=cors,
                    allow_methods=cors,
                    allow_headers=cors,
                )

            API._original_openapi = self.app.openapi
            self.app.openapi = self._customize_openapi

            for exc_type, handler in (
                (RequestValidationError, self._handle_request_validation),
                (ResponseValidationError, self._handle_response_validation),
                (BaseError, self._handle_base_error),
                (Exception, self._handle_unexpected_error),
            ):
                self.app.exception_handler(exc_type)(handler)

            self.app.router.lifespan_context = self._lifespan
            self.app.include_router(authentication.router)
            self.app.include_router(packages.router)

            self._server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
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
    def _replace_refs(obj: object, old_ref: str, new_ref: str) -> None:
        """Recursively replaces all `$ref` values in the OpenAPI schema."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "$ref" and value == old_ref:
                    obj[key] = new_ref
                else:
                    API._replace_refs(value, old_ref, new_ref)
        elif isinstance(obj, list):
            for item in obj:
                API._replace_refs(item, old_ref, new_ref)

    @staticmethod
    def _customize_openapi() -> dict:
        """
        Customizes the OpenAPI schema by removing FastAPI's auto-generated
        validation error schemas and renaming ``SerializedError`` to ``BaseError``.
        """
        schema = API._original_openapi()
        schemas = schema.get("components", {}).get("schemas", {})
        schemas.pop("HTTPValidationError", None)
        schemas.pop("SerializedError", None)

        # Replacing leftover ``SerializedError`` references
        # from the `cause` annotation with ``BaseError``
        API._replace_refs(
            schema,
            f"#/components/schemas/{SerializedError.__name__}",
            f"#/components/schemas/{BaseError.__name__}",
        )

        return schema

    @staticmethod
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": "ValidationError",
                "message": "Request validation failed",
                "cause": [
                    {
                        "error": error["type"],
                        "message": error["msg"],
                        "payload": {
                            "fields": list(error["loc"]),
                            "input": error.get("input"),
                        },
                    }
                    for error in exc.errors()
                ],
            },
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @staticmethod
    async def _handle_response_validation(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        logger.exception(
            f"Response validation error on path '{request.url.path}'",
            exc_info=exc,
        )

        return JSONResponse(
            {
                "error": "ResponseValidationError",
                "message": "Response validation failed",
                "cause": [
                    {
                        "error": error["type"],
                        "message": error["msg"],
                        "payload": {"fields": list(error["loc"])},
                    }
                    for error in exc.errors()
                ],
            },
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @staticmethod
    async def _handle_base_error(request: Request, exc: BaseError) -> JSONResponse:
        return JSONResponse(exc.serialize(), status_code=exc.http_code)

    @staticmethod
    async def _handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            UnexpectedError(
                "Unexpected error happened in the API",
                cause=exc,
                payload={"path": request.url.path},
            )
        )

        error = UnexpectedError()
        return JSONResponse(error.serialize(), status_code=error.http_code)

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
