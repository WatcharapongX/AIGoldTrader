"""One validated correlation identity for request headers, logs and audit writes."""

import contextvars
import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_CORRELATION_ID_LENGTH = 64
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def normalize_correlation_id(value: str | None) -> str:
    return value if value is not None and _SAFE_ID.fullmatch(value) else new_correlation_id()


def set_correlation_id(value: str | None) -> contextvars.Token[str]:
    return _correlation_id.set(normalize_correlation_id(value))


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    return _correlation_id.get()


class CorrelationMiddleware:
    """Pure ASGI: reset only after the response/body/background lifecycle completes."""

    def __init__(self, app: ASGIApp, on_error: Callable[[Request, Exception], Awaitable[Response]]) -> None:
        self.app = app
        self.on_error = on_error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = set_correlation_id(Headers(scope=scope).get("X-Correlation-ID"))
        correlation_id = get_correlation_id()
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        started = False

        async def send_with_correlation(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)["X-Correlation-ID"] = correlation_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_correlation)
            except Exception as exc:  # noqa: BLE001 — same controlled error policy as the existing middleware
                response = await self.on_error(Request(scope), exc)
                if started:
                    # A streaming response cannot be replaced after headers; retain the safe error log.
                    raise
                await response(scope, receive, send_with_correlation)
        finally:
            reset_correlation_id(token)
