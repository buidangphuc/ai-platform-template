from uuid import uuid4

from fastapi import APIRouter, Request

from app.api.v1.completions.observability import (
    CompletionTimer,
    Outcome,
    completion_sink,
)
from app.bootstrap.state import get_app_resources
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResponse,
)

router = APIRouter()


@router.post("", response_model=CompletionResponse)
async def complete(
    payload: CompletionRequest,
    request: Request,
) -> CompletionResponse:
    resources = get_app_resources(request.app)
    service = resources.completion_service
    timer = CompletionTimer(mode="sync", sink=completion_sink(resources))
    outcome: Outcome = "error"
    try:
        result = await service.complete(payload)
        timer.observe(
            model=result.model,
            usage=result.usage,
            finish_reason=result.finish_reason,
        )
        outcome = "ok"
    finally:
        timer.emit(outcome)
    return CompletionResponse(
        id=f"cmpl_{uuid4().hex}",
        content=result.content,
        model=result.model,
        usage=result.usage,
        finish_reason=result.finish_reason,
        metadata=result.metadata,
    )
