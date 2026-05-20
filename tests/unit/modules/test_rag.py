from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.llm.fake import FakeLLMClient
from app.adapters.observability.debug import DebugObservability
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.core.redaction import RedactionPolicy
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.schemas import RagAnswerRequest, RagDocument, RagIndexRequest
from app.modules.rag.service import RagService
from app.modules.usage.tracker import InMemoryUsageTracker


def build_rag_service() -> RagService:
    return RagService(
        embeddings=FakeEmbeddingClient(model="fake-embedding", dimensions=8),
        vector_store=InMemoryVectorStore(),
        llm=FakeLLMClient(model="fake-chat"),
        prompt_registry=InMemoryPromptRegistry.with_defaults(),
        chunker=TextChunker(chunk_size=8, overlap=2),
        usage_tracker=InMemoryUsageTracker(),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )


async def test_rag_service_indexes_searches_and_answers_with_fake_adapters():
    service = build_rag_service()
    await service.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="adapter contracts make provider swaps safer",
                    metadata={"source": "phase-2"},
                ),
            ],
        )
    )

    search = await service.search("adapter contracts", top_k=1)
    answer = await service.answer(
        RagAnswerRequest(question="What makes provider swaps safer?", top_k=1)
    )

    assert search.matches[0].document_id == "doc-1"
    assert "adapter contracts" in search.matches[0].text
    assert answer.answer.startswith("fake-chat response:")
    assert answer.sources[0].document_id == "doc-1"
    assert answer.usage.total_tokens > 0
    assert service.usage_tracker.records


def test_text_chunker_uses_overlap_without_empty_chunks():
    chunks = TextChunker(chunk_size=4, overlap=1).chunk_document(
        document_id="doc-1",
        text="one two three four five six seven",
        metadata={"source": "unit"},
    )

    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        "four five six seven",
    ]
    assert chunks[0].metadata["chunk_index"] == 0
