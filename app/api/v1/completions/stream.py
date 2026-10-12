import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.bootstrap.state import get_app_resources
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionStreamChunk,
)
from app.modules.business.completions.service import CompletionService

router = APIRouter()


@router.post("/stream")
async def stream(
    payload: CompletionRequest,
    request: Request,
) -> StreamingResponse:
    service = get_app_resources(request.app).completion_service
    return StreamingResponse(
        stream_completion_events(service, payload),
        media_type="text/event-stream",
    )


async def stream_completion_events(
    service: CompletionService,
    payload: CompletionRequest,
) -> AsyncIterator[str]:
    async for chunk in service.stream(payload):
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
