"""Server-sent events for feature streams.

Contract: the first event is awaited before the response exists, so an error
before it (guard violation, handler startup failure, first-token timeout) is a
normal JSON error. After that the status is already 200, so a failure becomes an
``event: error`` frame carrying a safe code (never exception text) and the
stream closes. ``: ping`` comments keep proxies from idling out while waiting.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass

import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.bootstrap.state import get_app_settings
from app.core.errors import AppError

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
PING = ": ping\n\n"
STREAM_ERROR_CODE = "stream_error"


@dataclass(frozen=True)
class ServerSentEvent:
    data: dict[str, object]
    event: str | None = None

    def encode(self) -> str:
        prefix = f"event: {self.event}\n" if self.event else ""
        return f"{prefix}data: {json.dumps(self.data)}\n\n"


async def event_stream_response(
    request: Request,
    events: AsyncGenerator[ServerSentEvent, None],
) -> StreamingResponse:
    """Prime the first event (errors raise here), then stream the rest."""
    heartbeat = get_app_settings(request.app).SSE_HEARTBEAT_SECONDS
    try:
        first = await anext(events)
    except BaseException:
        await events.aclose()
        raise
    return StreamingResponse(
        _frames(first, events, heartbeat),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _next(
    events: AsyncGenerator[ServerSentEvent, None],
) -> ServerSentEvent | None:
    return await anext(events, None)


async def _frames(
    first: ServerSentEvent,
    events: AsyncGenerator[ServerSentEvent, None],
    heartbeat: float,
) -> AsyncIterator[str]:
    pending: asyncio.Task[ServerSentEvent | None] | None = None
    try:
        event: ServerSentEvent | None = first
        while event is not None:
            yield event.encode()
            pending = asyncio.create_task(_next(events))
            while not (await asyncio.wait({pending}, timeout=heartbeat))[0]:
                yield PING
            event = pending.result()
    except AppError as exc:
        yield _error_frame(exc.code)
    except Exception:
        logger.exception("sse.stream_failed")
        yield _error_frame(STREAM_ERROR_CODE)
    finally:
        # A client disconnect cancels this generator under an anyio cancel scope,
        # which re-cancels every await: cleanup must run shielded.
        with anyio.CancelScope(shield=True):
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.wait({pending})
            await events.aclose()


def _error_frame(code: str) -> str:
    return ServerSentEvent({"type": "error", "code": code}, event="error").encode()
