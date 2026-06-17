import asyncio

import pytest
from fastapi import FastAPI
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.node_parser import SentenceSplitter

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.redaction import RedactionPolicy
from app.core.resilience import TimeoutPolicy
from app.modules.ai.rag.factory import RagAddon, build_rag_service
from app.modules.ai.rag.service import (
    KnowledgeRetrievalService,
    build_rag_node_parser,
)
from tests.factories import build_test_settings


def build_knowledge_service(
    *,
    default_top_k: int = 5,
    retrieve_timeout: TimeoutPolicy | None = None,
) -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        redaction_policy=RedactionPolicy(mode="redacted"),
        default_top_k=default_top_k,
        retrieve_timeout=retrieve_timeout,
    )


async def test_knowledge_service_indexes_and_searches_with_llamaindex_runtime():
    service = build_knowledge_service()
    await service.index(
        [
            Document(
                id_="doc-1",
                text="adapter contracts make provider swaps safer",
                metadata={"source": "phase-2"},
            ),
        ]
    )

    search = await service.search("adapter contracts", top_k=1)

    assert search[0].node.metadata["document_id"] == "doc-1"
    assert "adapter contracts" in search[0].node.text
    assert isinstance(service.index_store, VectorStoreIndex)


async def test_knowledge_service_redacts_content_before_vector_storage():
    service = build_knowledge_service()

    await service.index(
        [
            Document(
                id_="doc-1",
                text="Contact admin@example.com with Bearer abc123",
                metadata={"api_key": "sk-secret-value"},  # pragma: allowlist secret
            ),
        ]
    )

    search = await service.search("Contact", top_k=1)

    assert "admin@example.com" not in search[0].node.text
    assert "Bearer abc123" not in search[0].node.text
    assert search[0].node.metadata["api_key"] == "[secret]"


async def test_rag_ingestion_preserves_llamaindex_node_metadata_shape():
    service = build_knowledge_service()

    await service.index(
        [
            Document(
                id_="doc-1",
                text="LlamaIndex nodes carry text and metadata.",
                metadata={"source": "unit"},
            ),
        ]
    )

    search = await service.search("metadata", top_k=1)

    assert search[0].node.text == "LlamaIndex nodes carry text and metadata."
    assert search[0].node.metadata["document_id"] == "doc-1"
    assert search[0].node.node_id == "doc-1:chunk:0"
    assert search[0].node.metadata["source"] == "unit"


def test_rag_node_parser_uses_deterministic_chunk_ids():
    parser = build_rag_node_parser(chunk_size=64, chunk_overlap=8)

    assert isinstance(parser, SentenceSplitter)
    assert parser.id_func(0, Document(text="content", id_="doc-1")) == "doc-1:chunk:0"


async def test_index_empty_documents_returns_zero_counts():
    service = build_knowledge_service()

    result = await service.index([])

    assert result == {"indexed_count": 0, "chunk_count": 0}


async def test_index_is_incremental_and_does_not_re_embed_existing_docs():
    service = build_knowledge_service()

    await service.index(
        [Document(id_="doc-1", text="first document content", metadata={})]
    )
    await service.index(
        [Document(id_="doc-2", text="second document content", metadata={})]
    )

    search = await service.search("document", top_k=5)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {"doc-1", "doc-2"}


async def test_delete_removes_document_chunks_from_index():
    service = build_knowledge_service()
    await service.index(
        [
            Document(id_="doc-1", text="first document", metadata={}),
            Document(id_="doc-2", text="second document", metadata={}),
        ]
    )

    await service.delete("doc-1")

    search = await service.search("document", top_k=5)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {"doc-2"}


async def test_search_uses_metadata_filter_pre_retrieval():
    service = build_knowledge_service()
    await service.index(
        [
            Document(id_="doc-a", text="alpha content", metadata={"tenant": "a"}),
            Document(id_="doc-b", text="alpha content", metadata={"tenant": "b"}),
        ]
    )

    search = await service.search("alpha", top_k=5, filters={"tenant": "a"})

    tenants = {match.node.metadata["tenant"] for match in search}
    assert tenants == {"a"}


async def test_concurrent_index_calls_are_serialized():
    service = build_knowledge_service()

    async def index_doc(doc_id: str) -> None:
        await service.index(
            [Document(id_=doc_id, text=f"content of {doc_id}", metadata={})]
        )

    await asyncio.gather(*(index_doc(f"doc-{i}") for i in range(5)))

    search = await service.search("content", top_k=10)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {f"doc-{i}" for i in range(5)}


async def test_search_respects_retrieve_timeout():
    service = build_knowledge_service(
        retrieve_timeout=TimeoutPolicy(timeout_seconds=0.001),
    )
    await service.index([Document(id_="doc-1", text="some content", metadata={})])

    original_aretrieve = service.index_store.as_retriever().aretrieve

    async def slow_aretrieve(query: str):
        await asyncio.sleep(1)
        return await original_aretrieve(query)

    retriever = service.index_store.as_retriever()
    retriever.aretrieve = slow_aretrieve  # type: ignore[method-assign]
    service.index_store.as_retriever = lambda **_: retriever  # type: ignore[method-assign]

    with pytest.raises(asyncio.TimeoutError):
        await service.search("content")


def _rag_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"RAG_ENABLED": True}
    base.update(overrides)
    return build_test_settings(**base)


def test_build_rag_service_uses_settings_defaults():
    service = build_rag_service(_rag_settings())

    assert isinstance(service, KnowledgeRetrievalService)
    assert service.default_top_k == 5
    assert service.retrieve_timeout is not None


def test_rag_addon_respects_enabled_flag():
    addon = RagAddon()

    assert addon.is_enabled(_rag_settings()) is True
    assert addon.is_enabled(_rag_settings(RAG_ENABLED=False)) is False


async def test_rag_addon_attaches_service_when_enabled():
    app = FastAPI()
    resources = ApplicationResources()
    addon = RagAddon()

    await addon.open(app, resources, _rag_settings())

    assert isinstance(resources.rag_service, KnowledgeRetrievalService)


def test_build_embed_model_raises_for_unimplemented_provider():
    from app.modules.ai.rag.factory import build_embed_model

    with pytest.raises(RuntimeError, match="not implemented"):
        build_embed_model(
            _rag_settings(RAG_EMBED_MODEL="openai:text-embedding-3-small")
        )
