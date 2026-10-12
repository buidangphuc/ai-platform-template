from uuid import uuid4

from fastapi import APIRouter, Request

from app.api.v1.completions.observability import CompletionTimer, Outcome
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
    service = get_app_resources(request.app).completion_service
    timer = CompletionTimer(mode="sync")
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
