from collections.abc import AsyncGenerator
from contextlib import aclosing

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.sse import ServerSentEvent, event_stream_response
from app.bootstrap.state import get_app_resources
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResponse,
    CompletionStreamChunk,
    StreamSummary,
)
from app.modules.platform.identity.auth import require_principal

router = APIRouter(
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)


@router.post("", response_model=CompletionResponse)
async def complete(payload: CompletionRequest, request: Request) -> CompletionResponse:
    service = get_app_resources(request.app).completion_service
    result = await service.complete(payload)
    return CompletionResponse.model_validate(result, from_attributes=True)


@router.post("/stream")
async def stream(payload: CompletionRequest, request: Request) -> StreamingResponse:
    service = get_app_resources(request.app).completion_service
    return await event_stream_response(request, _events(service.stream(payload)))


async def _events(
    chunks: AsyncGenerator[CompletionStreamChunk, None],
) -> AsyncGenerator[ServerSentEvent, None]:
    summary = StreamSummary()
    async with aclosing(chunks):
        async for chunk in chunks:
            summary.merge(chunk)
            if chunk.delta:
                yield ServerSentEvent(
                    {
                        "type": "content.delta",
                        "delta": chunk.delta,
                        "metadata": chunk.metadata,
                    }
                )
    done = {"type": "done", **summary.model_dump(exclude_none=True)}
    yield ServerSentEvent(done)
