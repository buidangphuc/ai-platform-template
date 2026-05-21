"""Sync completion endpoint — caller waits for the full response."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from app.api.v1.completions.deps import get_completion_handler
from app.api.v1.completions.schemas import CompletionRequest, CompletionResponse
from app.modules.identity.auth import require_principal

router = APIRouter(
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)


@router.post("", response_model=CompletionResponse)
async def complete(payload: CompletionRequest, request: Request):
    handler = get_completion_handler(request)
    result = await handler.complete(payload)
    return CompletionResponse(
        id=f"cmpl_{uuid4().hex}",
        content=result.content,
        model=result.model,
        metadata=result.metadata,
    )
