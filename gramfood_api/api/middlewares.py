from collections.abc import Callable, Awaitable

from fastapi import Response
from starlette.types import ASGIApp
from starlette.middleware.base import BaseHTTPMiddleware

from .types import Request
from .dependencies import get_connection
from .errors import InvalidSessionError, NotAuthenticatedError
from ..services.authentication import AuthenticationService

AUTHENTICATION_EXCLUDED_ROUTES = {
    "/openapi.json",
    "/api",
    "/authentication/request-otp",
    "/authentication/verify-otp",
    "/authentication/verify-token",
}


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware that verifies session tokens for protected routes."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._authentication_service = AuthenticationService(get_connection())

    @staticmethod
    def get_token(request: Request) -> str | None:
        """Extracts the bearer token from the Authorization header or cookie."""
        if authorization := request.headers.get("authorization"):
            scheme, _, header_token = authorization.partition(" ")
            if scheme.lower() == "bearer":
                return header_token
            return None

        return request.cookies.get("token")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path not in AUTHENTICATION_EXCLUDED_ROUTES:
            token = self.get_token(request)
            if not token:
                raise NotAuthenticatedError()

            user = self._authentication_service.get_user(token)
            if user is None:
                raise InvalidSessionError()

            request.state.user = user

        return await call_next(request)
