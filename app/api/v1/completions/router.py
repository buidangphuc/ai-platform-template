from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.sse import ServerSentEvent, event_stream_response
from app.api.v1.completions import tasks
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

# Mounted only when TASKS_ENABLED (see app/api/router.py).
tasks_router = APIRouter(prefix="/completions", tags=["completions"])
tasks_router.include_router(tasks.router)


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
    try:
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
    finally:
        await chunks.aclose()
    done: dict[str, object] = {"type": "done"}
    if summary.usage is not None:
        done["usage"] = summary.usage.model_dump()
    if summary.finish_reason is not None:
        done["finish_reason"] = summary.finish_reason
    if summary.model is not None:
        done["model"] = summary.model
    yield ServerSentEvent(done)
