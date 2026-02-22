from typing import Any, ClassVar, TypedDict
from collections.abc import Sequence

from httpx import codes

from .types import SerializedError


class BaseError(Exception):
    """The base exception that can be inherited by the other exceptions.

    Attributes:
        `message`:
            The error message.
        `code`:
            The error code.
        `http_code`:
            The HTTP error code that would be used for the RESTful API.
        `cause`:
            The exception that will be stored as `__cause__` attribute.
            `ValueError` will be raised if value is not an exception.
        `payload`:
            The serializable value that could be stored for any use case.
        `expose_payload`:
            Whether the `payload` attribute should be included in the
            serialized version of the exception.
    """

    _openapi_models: ClassVar[dict[str, type]] = {}

    def __init__(
        self,
        message: str,
        code: int,
        *,
        http_code: int | None = None,
        cause: BaseException | None = None,
        payload: Any = None,
        expose_payload: bool = True,
    ) -> None:
        self.message = message
        self.code = code
        self.http_code = http_code
        self.payload = payload
        self.expose_payload = expose_payload
        if cause:
            if not isinstance(cause, Exception):
                raise ValueError(
                    "The 'cause' parameter must be instance of the 'Exception' class"
                )
            self.__cause__ = cause

    def __str__(self) -> str:
        return self.message

    def __repr__(self, indent: int = 0) -> str:
        parts = [self.message]
        if indent == 0:
            parts.insert(0, f"[{self.__class__.__name__}] ")

        if isinstance(self.payload, dict):
            if payload_str := " ".join(f"{k}={v}" for k, v in self.payload.items()):
                parts.append(f" | {payload_str}")
        elif self.payload is not None:
            parts.append(f" | payload={self.payload!r}")

        if cause := self.__cause__:
            stack = [(cause, 1)]
            while stack:
                exception, extra_indent = stack.pop(0)
                parts.append(
                    f"\n{'  ' * (indent + extra_indent)}↳ [{exception.__class__.__name__}] "
                )
                if isinstance(exception, ExceptionGroup):
                    parts.append(exception.message)
                    stack[0:0] = [
                        (exception, extra_indent + 1)
                        for exception in exception.exceptions
                    ]
                else:
                    parts.append(
                        exception.__repr__(indent + extra_indent)
                        if isinstance(exception, BaseError)
                        else repr(exception)
                    )

        return "".join(parts)

    def _serialize_exception(
        self, exception: Exception, _group: str | None = None
    ) -> SerializedError | list[SerializedError]:
        if isinstance(exception, ExceptionGroup):
            group = exception.message
            errors = [
                self._serialize_exception(exec, group) for exec in exception.exceptions
            ]
            return errors[0] if len(errors) == 1 else errors

        serialized = {"error": exception.__class__.__name__, "message": str(exception)}
        if _group:
            serialized["group"] = _group
        if isinstance(exception, BaseError):
            serialized["code"] = exception.code
            if exception.__cause__:
                cause = self._serialize_exception(exception.__cause__)
                serialized["cause"] = cause if type(cause) is list else [cause]
            if exception.payload is not None and exception.expose_payload:
                serialized["payload"] = exception.payload

        return serialized

    def serialize(self) -> SerializedError:
        """Returns the serializable version of the exception."""
        serialized = self._serialize_exception(self)
        return serialized if type(serialized) is not list else serialized[0]

    @staticmethod
    def create_exception_group(
        message: str, exceptions: Sequence[Exception] | Exception | None
    ) -> ExceptionGroup | None:
        """Wraps the given exceptions inside of an `ExceptionGroup`."""
        if exceptions:
            if isinstance(exceptions, Exception):
                if isinstance(exceptions, ExceptionGroup):
                    return exceptions
                exceptions = (exceptions,)
            return ExceptionGroup(message, exceptions)

    @classmethod
    def openapi_model(cls) -> type:
        """Dynamically generates a `TypedDict` for OpenAPI schema representation."""
        class_name = cls.__name__
        if class_name not in cls._openapi_models:
            cls._openapi_models[class_name] = TypedDict(
                class_name, SerializedError.__annotations__
            )

        return cls._openapi_models[class_name]


class UnexpectedError(BaseError):
    """Unexpected error happened."""

    def __init__(self, message: str = "Unexpected error happened", **kwargs) -> None:
        super().__init__(message, 0, http_code=codes.INTERNAL_SERVER_ERROR, **kwargs)
