"""Pure-ASGI middleware: request ids, security headers, body-size limits."""
import re
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import structlog

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class RequestContextMiddleware:
    """Assigns a request id (client value accepted only if well-formed) and binds it to logs."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else secrets.token_hex(8)
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_id)


class SecurityHeadersMiddleware:
    """API responses are JSON/redirects only: lock everything down and never cache."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, hsts: bool) -> None:
        self.app = app
        self.headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"cache-control", b"no-store"),
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
            (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
            (b"cross-origin-resource-policy", b"same-origin"),
        ]
        if hsts:
            self.headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_secure(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    h for h in self.headers if h[0] not in existing
                ]
            await send(message)

        await self.app(scope, receive, send_secure)


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Rejects oversized bodies by Content-Length AND while streaming (chunked uploads)."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, default_limit: int, path_limits: dict[str, int]) -> None:
        self.app = app
        self.default_limit = default_limit
        self.path_limits = path_limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.path_limits.get(scope["path"], self.default_limit)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            return await self._reject(send)

        started = False
        received = 0

        async def limited_receive() -> MutableMapping[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: MutableMapping[str, Any]) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"error":"payload_too_large"}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
