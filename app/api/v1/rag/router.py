from fastapi import APIRouter, Depends, Request, status

from app.modules.identity.auth import require_authenticated_request
from app.modules.rag.schemas import (
    RagAnswerRequest,
    RagAnswerResponse,
    RagIndexRequest,
    RagIndexResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from app.modules.rag.service import RagService

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    dependencies=[Depends(require_authenticated_request)],
)


def _service(request: Request) -> RagService:
    return request.app.state.rag_service


@router.post(
    "/index",
    response_model=RagIndexResponse,
    status_code=status.HTTP_201_CREATED,
)
async def index(payload: RagIndexRequest, request: Request):
    return await _service(request).index(payload)


@router.post("/search", response_model=RagSearchResponse)
async def search(payload: RagSearchRequest, request: Request):
    return await _service(request).search_request(payload)


@router.post("/answer", response_model=RagAnswerResponse)
async def answer(payload: RagAnswerRequest, request: Request):
    return await _service(request).answer(payload)
