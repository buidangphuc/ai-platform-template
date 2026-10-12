"""event_stream_response: priming, heartbeat, error frames, shielded close."""

import asyncio
import json
from collections.abc import AsyncGenerator

import anyio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.sse import PING, ServerSentEvent, event_stream_response
from app.core.errors import AppError, register_exception_handlers
from tests.factories import build_test_settings

type Events = AsyncGenerator[ServerSentEvent, None]


def test_event_encoding_matches_the_wire_format() -> None:
    assert (
        ServerSentEvent({"type": "done", "n": 1}).encode()
        == 'data: {"type": "done", "n": 1}\n\n'
    )
    assert (
        ServerSentEvent({"code": "x"}, event="error").encode()
        == 'event: error\ndata: {"code": "x"}\n\n'
    )


def _app(source, heartbeat: float = 10) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.settings = build_test_settings(SSE_HEARTBEAT_SECONDS=heartbeat)

    @app.get("/s")
    async def route(request: Request):
        return await event_stream_response(request, source())

    return app


async def _get(app: FastAPI) -> tuple[int, dict[str, str], str]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/s")
    return response.status_code, dict(response.headers), response.text


async def test_streams_events_with_sse_headers() -> None:
    async def source() -> Events:
        yield ServerSentEvent({"n": 1})
        yield ServerSentEvent({"n": 2})

    status, headers, body = await _get(_app(source))

    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"
    assert body == 'data: {"n": 1}\n\ndata: {"n": 2}\n\n'


async def test_error_before_the_first_event_stays_a_json_error() -> None:
    async def source() -> Events:
        raise AppError(code="nope", message="no", status_code=418)
        yield ServerSentEvent({})

    status, _, body = await _get(_app(source))

    assert status == 418
    assert json.loads(body)["error"]["code"] == "nope"


async def test_heartbeat_is_sent_while_waiting() -> None:
    async def source() -> Events:
        yield ServerSentEvent({"n": 1})
        await asyncio.sleep(0.2)
        yield ServerSentEvent({"n": 2})

    _, _, body = await _get(_app(source, heartbeat=0.05))

    assert PING in body
    assert body.endswith('data: {"n": 2}\n\n')


async def test_app_error_after_first_event_becomes_a_coded_error_frame() -> None:
    async def source() -> Events:
        yield ServerSentEvent({"n": 1})
        raise AppError(code="stream_timeout", message="slow", status_code=504)

    status, _, body = await _get(_app(source))

    assert status == 200
    assert body.endswith(
        'event: error\ndata: {"type": "error", "code": "stream_timeout"}\n\n'
    )


async def test_unexpected_error_becomes_a_safe_stream_error_frame() -> None:
    async def source() -> Events:
        yield ServerSentEvent({"n": 1})
        raise RuntimeError("secret detail")

    _, _, body = await _get(_app(source))

    assert body.endswith(
        'event: error\ndata: {"type": "error", "code": "stream_error"}\n\n'
    )
    assert "secret detail" not in body


async def test_close_runs_the_source_cleanup_even_when_cancelled() -> None:
    closed = asyncio.Event()

    async def source() -> Events:
        try:
            yield ServerSentEvent({"n": 1})
            await asyncio.sleep(30)
            yield ServerSentEvent({"n": 2})
        finally:
            await asyncio.sleep(0)  # an await a level-triggered cancel would break
            closed.set()

    app = FastAPI()
    app.state.settings = build_test_settings()
    response = await event_stream_response(
        Request({"type": "http", "app": app}), source()
    )

    with anyio.move_on_after(0.2):
        async for _ in response.body_iterator:
            pass

    assert closed.is_set()
