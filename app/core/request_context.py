from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_request_id = headers.get(self.header_name.lower().encode())
        request_id = raw_request_id.decode() if raw_request_id else f"req_{uuid4().hex}"
        set_request_id(request_id)

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append(
                    (self.header_name.encode(), request_id.encode())
                )
            await send(message)

        await self.app(scope, receive, send_with_request_id)
