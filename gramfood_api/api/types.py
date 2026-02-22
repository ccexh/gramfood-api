from fastapi import Request as DefaultRequest
from starlette.datastructures import State as DefaultState

from ..services.types import User


class State(DefaultState):
    user: User


class Request(DefaultRequest):
    """Typed wrapper for Starlette's request with typed state."""

    @property
    def state(self) -> State: ...
