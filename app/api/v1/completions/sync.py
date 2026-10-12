from uuid import uuid4

from fastapi import APIRouter, Request

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
    result = await service.complete(payload)
    return CompletionResponse(
        id=f"cmpl_{uuid4().hex}",
        content=result.content,
        model=result.model,
        metadata=result.metadata,
    )
