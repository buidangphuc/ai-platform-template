from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.llm.fake import FakeLLMClient
from app.adapters.observability.debug import DebugObservability
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.core.redaction import RedactionPolicy
from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalCase, RAGEvalRequest
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import RagService
from app.modules.usage.tracker import InMemoryUsageTracker


async def test_rag_eval_service_scores_keyword_hits_against_sources():
    rag = RagService(
        embeddings=FakeEmbeddingClient(model="fake-embedding", dimensions=8),
        vector_store=InMemoryVectorStore(),
        llm=FakeLLMClient(model="fake-chat"),
        prompt_registry=InMemoryPromptRegistry.with_defaults(),
        chunker=TextChunker(chunk_size=32, overlap=0),
        usage_tracker=InMemoryUsageTracker(),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await rag.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="Phase three adds prompt registry and RAG evaluation.",
                )
            ]
        )
    )
    service = RAGEvaluationService(rag_service=rag)

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
