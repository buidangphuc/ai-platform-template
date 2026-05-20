from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> Token[str]:
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def _first_header(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    lowercase_name = name.lower()
    for header_name, header_value in headers:
        if header_name.lower() == lowercase_name:
            return header_value
    return None


def _set_response_header(
    headers: list[tuple[bytes, bytes]], name: bytes, value: bytes
) -> None:
    lowercase_name = name.lower()
    headers[:] = [
        (header_name, header_value)
        for header_name, header_value in headers
        if header_name.lower() != lowercase_name
    ]
    headers.append((name, value))


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header_name = self.header_name.encode()
        headers = scope.get("headers") or []
        raw_request_id = _first_header(headers, header_name)
        request_id = raw_request_id.decode() if raw_request_id else f"req_{uuid4().hex}"
        token = set_request_id(request_id)

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                _set_response_header(
                    message["headers"], header_name, request_id.encode()
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)
