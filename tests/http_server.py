from __future__ import annotations

import asyncio
import json as jsonlib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import pytest


@dataclass(frozen=True)
class Reply:
    status: int = 200
    json: Any = None
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    delay: float = 0.0
    drop: bool = False


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    query: str
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        return jsonlib.loads(self.body)


class LocalHttpServer:
    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self._scripts: dict[str, list[Reply]] = {}
        self._served: dict[str, int] = {}
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self.url = ""

    def script(self, path: str, *replies: Reply) -> None:
        self._scripts[path] = list(replies) or [Reply()]
        self._served[path] = 0

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.path == path]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        for writer in list(self._writers):
            writer.transport.abort()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def _next_reply(self, path: str) -> Reply:
        replies = self._scripts.get(path)
        if replies is None:
            return Reply(status=404)
        index = min(self._served[path], len(replies) - 1)
        self._served[path] += 1
        return replies[index]

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.add(writer)
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            request = await self._read_request(reader)
            self.requests.append(request)
            reply = self._next_reply(request.path)
            if reply.delay:
                await asyncio.sleep(reply.delay)
            if reply.drop:
                writer.transport.abort()
                return
            writer.write(_render(reply))
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.CancelledError):
            pass
        finally:
            self._writers.discard(writer)
            if task is not None:
                self._tasks.discard(task)
            writer.close()

    async def _read_request(self, reader: asyncio.StreamReader) -> RecordedRequest:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {
            name.strip().lower(): value.strip()
            for name, _, value in (line.partition(":") for line in lines[1:] if line)
        }
        body = await reader.readexactly(int(headers.get("content-length", 0)))
        path, _, query = target.partition("?")
        return RecordedRequest(method, path, query, headers, body)


def _render(reply: Reply) -> bytes:
    body = jsonlib.dumps(reply.json).encode() if reply.json is not None else reply.body
    headers = {
        "content-length": str(len(body)),
        "connection": "close",
        **({"content-type": "application/json"} if reply.json is not None else {}),
        **{name.lower(): value for name, value in reply.headers.items()},
    }
    status_line = f"HTTP/1.1 {reply.status} {HTTPStatus(reply.status).phrase}\r\n"
    head = status_line + "".join(f"{n}: {v}\r\n" for n, v in headers.items())
    return head.encode("latin-1") + b"\r\n" + body


@pytest.fixture()
async def local_http_server() -> AsyncIterator[LocalHttpServer]:
    server = LocalHttpServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()
