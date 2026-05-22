import asyncio
import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import get_request_id

access_logger = logging.getLogger("app.access")


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration_ms = (perf_counter() - started_at) * 1000
            state = scope.setdefault("state", {})
            principal = state.get("principal")
            principal_id = getattr(principal, "id", "-")
            request_id = state.get("request_id") or get_request_id()
            access_logger.info(
                "method=%s path=%s status=%s duration_ms=%.2f "
                "request_id=%s principal=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_code,
                duration_ms,
                request_id,
                principal_id,
            )


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await self._send_too_large(scope, send)
            return

        response_started = False
        bytes_received = 0

        async def receive_with_limit() -> Message:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                bytes_received += len(message.get("body") or b"")
                if bytes_received > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def send_with_state(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive_with_limit, send_with_state)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._send_too_large(scope, send)

    async def _send_too_large(self, scope: Scope, send: Send) -> None:
        request_id = _request_id_from_scope(scope)
        payload = {
            "error": {
                "code": "request_body_too_large",
                "message": "Request body too large",
                "request_id": request_id,
            }
        }
        body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"x-request-id", request_id.encode("utf-8")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _request_id_from_scope(scope: Scope) -> str:
    state = scope.setdefault("state", {})
    if state.get("request_id"):
        return str(state["request_id"])

    for name, value in scope.get("headers") or []:
        if name.lower() == b"x-request-id":
            request_id = value.decode("utf-8")
            state["request_id"] = request_id
            return request_id

    request_id = f"req_{uuid4().hex}"
    state["request_id"] = request_id
    return request_id


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or []:
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class RequestBodyTooLarge(Exception):
    pass


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        hsts_enabled: bool = False,
        hsts_max_age_seconds: int = 31536000,
    ) -> None:
        if hsts_max_age_seconds < 0:
            raise ValueError("hsts_max_age_seconds must not be negative")
        self.app = app
        self.hsts_enabled = hsts_enabled
        self.hsts_max_age_seconds = hsts_max_age_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("x-frame-options", "DENY")
                headers.setdefault("referrer-policy", "no-referrer")
                headers.setdefault(
                    "permissions-policy",
                    "camera=(), microphone=(), geolocation=()",
                )
                if self.hsts_enabled:
                    headers.setdefault(
                        "strict-transport-security",
                        (f"max-age={self.hsts_max_age_seconds}; includeSubDomains"),
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class InFlightTracker:
    def __init__(self) -> None:
        self._count = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def count(self) -> int:
        return self._count

    def acquire(self) -> None:
        self._count += 1
        self._idle.clear()

    def release(self) -> None:
        self._count = max(0, self._count - 1)
        if self._count == 0:
            self._idle.set()

    async def wait_idle(self, timeout: float) -> bool:
        if self._count == 0:
            return True
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False


class InFlightTrackerMiddleware:
    def __init__(self, app: ASGIApp, *, tracker: InFlightTracker) -> None:
        self.app = app
        self.tracker = tracker

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        self.tracker.acquire()
        try:
            await self.app(scope, receive, send)
        finally:
            self.tracker.release()


class RequestTimeoutMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout_seconds: float,
        exclude_patterns: tuple[str, ...] = (),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.app = app
        self.timeout_seconds = timeout_seconds
        self.exclude_patterns = exclude_patterns

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_excluded(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_with_state(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send_with_state),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            if response_started:
                raise
            await self._send_timeout(scope, send)

    def _is_excluded(self, path: str) -> bool:
        return any(pattern in path for pattern in self.exclude_patterns)

    async def _send_timeout(self, scope: Scope, send: Send) -> None:
        request_id = _request_id_from_scope(scope)
        payload = {
            "error": {
                "code": "request_timeout",
                "message": "Request exceeded timeout",
                "request_id": request_id,
            }
        }
        body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 504,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"x-request-id", request_id.encode("utf-8")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
