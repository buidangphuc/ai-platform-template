from uuid import uuid4

from app.modules.evals.schemas import RAGEvalItemResult, RAGEvalRequest, RAGEvalResult
from app.modules.rag.service import KnowledgeRetrievalService


class RAGEvaluationService:
    def __init__(self, *, knowledge_service: KnowledgeRetrievalService) -> None:
        self.knowledge_service = knowledge_service

    async def run(self, request: RAGEvalRequest) -> RAGEvalResult:
        items: list[RAGEvalItemResult] = []
        total_keywords = 0
        matched_keywords = 0
        for case in request.cases:
            search = await self.knowledge_service.search(
                case.question,
                top_k=request.top_k,
            )
            evidence = "\n\n".join(match.text for match in search.matches)
            evidence_text = evidence.lower()
            expected = [keyword.lower() for keyword in case.expected_keywords]
            matches = [keyword for keyword in expected if keyword in evidence_text]
            total_keywords += len(expected)
            matched_keywords += len(matches)
            items.append(
                RAGEvalItemResult(
                    id=case.id,
                    passed=len(matches) == len(expected),
                    matched_keywords=matches,
                    evidence=evidence,
                )
            )

        hit_rate = matched_keywords / total_keywords if total_keywords else 0.0
        return RAGEvalResult(
            run_id=str(uuid4()),
            items=items,
            metrics={"keyword_hit_rate": hit_rate},
        )
