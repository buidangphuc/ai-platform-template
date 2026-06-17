from uuid import uuid4

from fastapi import APIRouter, Request

from app.bootstrap.state import get_app_resources
from app.core.errors import AppError
from app.modules.business.completions.pipeline import CompletionPipeline
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResponse,
)

router = APIRouter()


def get_completion_pipeline(request: Request) -> CompletionPipeline:
    pipeline = get_app_resources(request.app).completion_pipeline
    if pipeline is None:
        raise AppError(
            code="completion_handler_not_configured",
            message="Completion handler is not configured",
            status_code=501,
        )
    return pipeline


@router.post("", response_model=CompletionResponse)
async def complete(
    payload: CompletionRequest,
    request: Request,
) -> CompletionResponse:
    pipeline = get_completion_pipeline(request)
    result = await pipeline.complete(payload)
    return CompletionResponse(
        id=f"cmpl_{uuid4().hex}",
        content=result.content,
        model=result.model,
        metadata=result.metadata,
    )
