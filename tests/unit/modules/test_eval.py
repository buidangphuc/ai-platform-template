from llama_index.core.embeddings import MockEmbedding

from app.core.redaction import RedactionPolicy
from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalCase, RAGEvalRequest
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import KnowledgeRetrievalService, build_rag_node_parser
from app.modules.usage.tracker import InMemoryUsageTracker


async def test_rag_eval_service_scores_keyword_hits_against_retrieved_evidence():
    knowledge = KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await knowledge.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="Phase three adds prompt registry and RAG evaluation.",
                )
            ]
        )
    )
    service = RAGEvaluationService(knowledge_service=knowledge)

    result = await service.run(
        RAGEvalRequest(
            cases=[
                RAGEvalCase(
                    id="case-1",
                    question="What does phase three add?",
                    expected_keywords=["prompt registry", "evaluation"],
                )
            ],
            top_k=1,
        )
    )

    assert result.metrics["keyword_hit_rate"] == 1.0
    assert result.items[0].passed is True
    assert "prompt registry" in result.items[0].evidence


async def test_rag_eval_service_fails_when_retrieval_misses_expected_keywords():
    knowledge = KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await knowledge.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="The source contains a hidden evaluation keyword.",
                )
            ]
        )
    )
    service = RAGEvaluationService(knowledge_service=knowledge)

    result = await service.run(
        RAGEvalRequest(
            cases=[
                RAGEvalCase(
                    id="case-1",
                    question="Return an unrelated answer.",
                    expected_keywords=["missing keyword"],
                )
            ],
            top_k=1,
        )
    )

    assert result.metrics["keyword_hit_rate"] == 0.0
    assert result.items[0].passed is False
