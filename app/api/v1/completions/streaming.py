"""Server-sent events for the completions stream.

Contract: errors that happen before the first chunk (guard violation, handler
startup failure, first-token timeout) are returned as normal JSON errors because
``open_event_stream`` awaits the first chunk before any header is sent. After
that point the status is already 200, so failures become an ``event: error``
frame with a safe code (never exception text), and the stream closes.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass

import anyio
from loguru import logger

from app.api.v1.completions.observability import CompletionTimer, Outcome
from app.core.errors import AppError
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionStreamChunk,
)
from app.modules.business.completions.service import CompletionService

STREAM_TIMEOUT_CODE = "stream_timeout"
STREAM_ERROR_CODE = "stream_error"
PING_FRAME = ": ping\n\n"
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class StreamTimeoutError(AppError):
    def __init__(self, message: str = "Timed out waiting for the model") -> None:
        super().__init__(code=STREAM_TIMEOUT_CODE, message=message, status_code=504)


@dataclass(frozen=True)
class StreamLimits:
    first_token_timeout: float
    idle_timeout: float
    heartbeat: float


def sse_event(payload: dict[str, object], *, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(payload)}\n\n"


async def open_event_stream(
    service: CompletionService,
    payload: CompletionRequest,
    limits: StreamLimits,
    timer: CompletionTimer,
) -> AsyncIterator[str]:
    """Await the first chunk, then return the SSE frames for the rest.

    Raises (before any response exists) whatever the guards or the handler raise,
    and ``StreamTimeoutError`` if no chunk arrives within the first-token deadline.
    """
    chunks = service.stream(payload)
    try:
        first = await asyncio.wait_for(
            anext(chunks, None), timeout=limits.first_token_timeout
        )
    except TimeoutError:
        await chunks.aclose()
        timer.emit("timeout")
        raise StreamTimeoutError from None
    except BaseException:
        await chunks.aclose()
        timer.emit("error")
        raise
    return _frames(first, chunks, limits, timer)


async def _next_chunk(
    chunks: AsyncGenerator[CompletionStreamChunk, None],
) -> CompletionStreamChunk | None:
    return await anext(chunks, None)


async def _frames(
    first: CompletionStreamChunk | None,
    chunks: AsyncGenerator[CompletionStreamChunk, None],
    limits: StreamLimits,
    timer: CompletionTimer,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    pending: asyncio.Task[CompletionStreamChunk | None] | None = None
    outcome: Outcome = "disconnected"  # what a cancelled/closed generator means
    chunk = first
    try:
        while chunk is not None:
            timer.observe(
                model=chunk.model,
                usage=chunk.usage,
                finish_reason=chunk.finish_reason,
            )
            if chunk.delta:
                timer.mark_first_token()
                yield sse_event(
                    {
                        "type": "content.delta",
                        "delta": chunk.delta,
                        "metadata": chunk.metadata,
                    }
                )
            pending = asyncio.create_task(_next_chunk(chunks))
            deadline = loop.time() + limits.idle_timeout
            while True:
                wait = min(limits.heartbeat, max(0.0, deadline - loop.time()))
                done, _ = await asyncio.wait({pending}, timeout=wait)
                if done:
                    break
                if loop.time() >= deadline:
                    raise StreamTimeoutError
                yield PING_FRAME
            chunk = pending.result()
    except StreamTimeoutError:
        outcome = "timeout"
        yield sse_event({"type": "error", "code": STREAM_TIMEOUT_CODE}, event="error")
    except Exception as exc:
        outcome = "error"
        logger.exception("completion.stream_failed")
        code = exc.code if isinstance(exc, AppError) else STREAM_ERROR_CODE
        yield sse_event({"type": "error", "code": code}, event="error")
    else:
        outcome = "ok"
        yield sse_event(_done_payload(timer))
    finally:
        # Record first: a client disconnect cancels this generator under an anyio
        # cancel scope, which re-cancels every await below.
        timer.emit(outcome)
        with anyio.CancelScope(shield=True):
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.wait({pending})
            await chunks.aclose()


def _done_payload(timer: CompletionTimer) -> dict[str, object]:
    payload: dict[str, object] = {"type": "done"}
    if timer.usage is not None:
        payload["usage"] = timer.usage.model_dump()
    if timer.finish_reason is not None:
        payload["finish_reason"] = timer.finish_reason
    if timer.model is not None:
        payload["model"] = timer.model
    return payload
