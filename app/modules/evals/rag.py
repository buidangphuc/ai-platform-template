from uuid import uuid4

from app.modules.evals.schemas import RAGEvalItemResult, RAGEvalRequest, RAGEvalResult
from app.modules.rag.schemas import RagAnswerRequest
from app.modules.rag.service import RagService


class RAGEvaluationService:
    def __init__(self, *, rag_service: RagService) -> None:
        self.rag_service = rag_service

    async def run(self, request: RAGEvalRequest) -> RAGEvalResult:
        items: list[RAGEvalItemResult] = []
        total_keywords = 0
        matched_keywords = 0
        for case in request.cases:
            answer = await self.rag_service.answer(
                RagAnswerRequest(question=case.question, top_k=request.top_k)
            )
            source_text = " ".join(source.text for source in answer.sources).lower()
            expected = [keyword.lower() for keyword in case.expected_keywords]
            matches = [keyword for keyword in expected if keyword in source_text]
            total_keywords += len(expected)
            matched_keywords += len(matches)
            items.append(
                RAGEvalItemResult(
                    id=case.id,
                    passed=len(matches) == len(expected),
                    matched_keywords=matches,
                    answer=answer.answer,
                )
            )

        hit_rate = matched_keywords / total_keywords if total_keywords else 0.0
        return RAGEvalResult(
            run_id=str(uuid4()),
            items=items,
            metrics={"keyword_hit_rate": hit_rate},
        )
