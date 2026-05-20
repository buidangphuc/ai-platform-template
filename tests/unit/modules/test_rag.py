from llama_index.core import Document, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.node_parser import SentenceSplitter

from app.core.redaction import RedactionPolicy
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import KnowledgeRetrievalService, build_rag_node_parser
from app.modules.usage.tracker import InMemoryUsageTracker


def build_knowledge_service() -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )


async def test_knowledge_service_indexes_and_searches_with_llamaindex_runtime():
    service = build_knowledge_service()
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

    assert search.matches[0].document_id == "doc-1"
    assert "adapter contracts" in search.matches[0].text
    assert service.usage_tracker.records
    assert isinstance(service.index_store, VectorStoreIndex)
    assert not hasattr(service, "vector_store")
    assert not hasattr(service, "answer")


async def test_knowledge_service_redacts_content_before_vector_storage():
    service = build_knowledge_service()

    await service.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="Contact admin@example.com with Bearer abc123",
                    metadata={"api_key": "sk-secret-value"},  # pragma: allowlist secret
                ),
            ],
        )
    )

    search = await service.search("Contact", top_k=1)

    assert "admin@example.com" not in search.matches[0].text
    assert "Bearer abc123" not in search.matches[0].text
    assert search.matches[0].metadata["api_key"] == "[secret]"


async def test_rag_ingestion_preserves_llamaindex_node_metadata_shape():
    service = build_knowledge_service()

    await service.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="LlamaIndex nodes carry text and metadata.",
                    metadata={"source": "unit"},
                ),
            ],
        )
    )

    search = await service.search("metadata", top_k=1)

    assert search.matches[0].text == "LlamaIndex nodes carry text and metadata."
    assert search.matches[0].document_id == "doc-1"
    assert search.matches[0].chunk_id == "doc-1:chunk:0"
    assert search.matches[0].metadata["document_id"] == "doc-1"
    assert search.matches[0].metadata["chunk_id"] == "doc-1:chunk:0"
    assert search.matches[0].metadata["source"] == "unit"


async def test_knowledge_service_invokes_reranker():
    class SpyReranker:
        def __init__(self) -> None:
            self.called = False

        def rerank(self, matches):
            self.called = True
            return list(reversed(matches))

    reranker = SpyReranker()
    service = build_knowledge_service()
    service.reranker = reranker
    await service.index(
        RagIndexRequest(
            documents=[
                RagDocument(id="doc-1", text="alpha beta"),
                RagDocument(id="doc-2", text="alpha gamma"),
            ],
        )
    )

    await service.search("alpha", top_k=2)

    assert reranker.called is True


def test_rag_node_parser_uses_deterministic_chunk_ids():
    parser = build_rag_node_parser(chunk_size=64, chunk_overlap=8)

    assert isinstance(parser, SentenceSplitter)
    assert parser.id_func(0, Document(text="content", id_="doc-1")) == "doc-1:chunk:0"
