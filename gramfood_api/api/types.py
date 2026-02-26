from typing import Any

from pydantic import TypeAdapter
from fastapi import Request as DefaultRequest
from fastapi.responses import JSONResponse as DefaultJSONResponse
from starlette.datastructures import State as DefaultState

from ..services.types import User


class State(DefaultState):
    user: User


class Request(DefaultRequest):
    """Typed wrapper for Starlette's request with typed state."""

    @property
    def state(self) -> State: ...


class JSONResponse(DefaultJSONResponse):
    """JSON response that uses Pydantic's Rust-based serializer."""

    _adapter = TypeAdapter(Any)

    def render(self, content: Any) -> bytes:
        return self._adapter.dump_json(content)
