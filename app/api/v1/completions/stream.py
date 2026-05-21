"""SSE streaming completion endpoint."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.v1.completions.deps import get_completion_handler
from app.api.v1.completions.handler import CompletionHandler
from app.api.v1.completions.schemas import CompletionRequest, CompletionStreamChunk
from app.modules.identity.auth import require_principal

router = APIRouter(
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)


@router.post("/stream")
async def stream(payload: CompletionRequest, request: Request):
    handler = get_completion_handler(request)
    return StreamingResponse(
        stream_completion_events(handler, payload),
        media_type="text/event-stream",
    )


async def stream_completion_events(
    handler: CompletionHandler,
    payload: CompletionRequest,
) -> AsyncIterator[str]:
    async for chunk in handler.stream(payload):
        stream_chunk = normalize_stream_chunk(chunk)
        if stream_chunk.delta:
            yield sse_event(
                {
                    "type": "content.delta",
                    "delta": stream_chunk.delta,
                    "metadata": stream_chunk.metadata,
                }
            )
    yield sse_event({"type": "done"})


def normalize_stream_chunk(
    chunk: CompletionStreamChunk | str,
) -> CompletionStreamChunk:
    if isinstance(chunk, str):
        return CompletionStreamChunk(delta=chunk)
    return chunk


def sse_event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
