from fastapi import APIRouter, Request

from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalRequest, RAGEvalResult

router = APIRouter(prefix="/evals", tags=["evals"])


def _service(request: Request) -> RAGEvaluationService:
    return request.app.state.rag_eval_service


@router.post("/rag", response_model=RAGEvalResult)
async def run_rag_eval(payload: RAGEvalRequest, request: Request):
    return await _service(request).run(payload)
