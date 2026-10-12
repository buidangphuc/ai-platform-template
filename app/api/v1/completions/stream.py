from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.v1.completions.observability import CompletionTimer, completion_sink
from app.api.v1.completions.streaming import (
    SSE_HEADERS,
    StreamLimits,
    open_event_stream,
)
from app.bootstrap.state import get_app_resources, get_app_settings
from app.modules.business.completions.schemas import CompletionRequest

router = APIRouter()


@router.post("/stream")
async def stream(
    payload: CompletionRequest,
    request: Request,
) -> StreamingResponse:
    resources = get_app_resources(request.app)
    service = resources.completion_service
    settings = get_app_settings(request.app)
    # Awaits the first chunk: guard/handler errors surface here as JSON errors.
    events = await open_event_stream(
        service,
        payload,
        StreamLimits(
            first_token_timeout=settings.STREAM_FIRST_TOKEN_TIMEOUT_SECONDS,
            idle_timeout=settings.STREAM_IDLE_TIMEOUT_SECONDS,
            heartbeat=settings.SSE_HEARTBEAT_SECONDS,
        ),
        CompletionTimer(mode="stream", sink=completion_sink(resources)),
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
