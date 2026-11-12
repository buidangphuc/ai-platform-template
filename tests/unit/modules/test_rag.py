import asyncio

import pytest
from fastapi import FastAPI
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bootstrap.addons.rag import RagAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.ai.rag.factory import build_embed_model, build_rag_service
from app.modules.ai.rag.service import (
    KnowledgeRetrievalService,
    build_rag_node_parser,
)
from tests.factories import build_test_settings, open_addon


async def test_knowledge_service_indexes_and_searches(rag_service):
    await rag_service.index(
        [
            Document(
                id_="doc-1",
                text="adapter contracts make provider swaps safer",
                metadata={"source": "phase-2"},
            ),
        ]
    )

    search = await rag_service.search("adapter contracts", top_k=1)

    assert search[0].node.metadata["document_id"] == "doc-1"
    assert "adapter contracts" in search[0].node.text


async def test_knowledge_service_redacts_content_before_vector_storage(rag_service):
    await rag_service.index(
        [
            Document(
                id_="doc-1",
                text="Contact admin@example.com with Bearer abc123",
                metadata={"api_key": "sk-secret-value"},  # pragma: allowlist secret
            ),
        ]
    )

    search = await rag_service.search("Contact", top_k=1)

    assert "admin@example.com" not in search[0].node.text
    assert "Bearer abc123" not in search[0].node.text
    assert search[0].node.metadata["api_key"] == "[secret]"


async def test_rag_ingestion_preserves_llamaindex_node_metadata_shape(rag_service):
    await rag_service.index(
        [
            Document(
                id_="doc-1",
                text="LlamaIndex nodes carry text and metadata.",
                metadata={"source": "unit"},
            ),
        ]
    )

    search = await rag_service.search("metadata", top_k=1)

    assert search[0].node.text == "LlamaIndex nodes carry text and metadata."
    assert search[0].node.metadata["document_id"] == "doc-1"
    assert search[0].node.node_id == "doc-1:chunk:0"
    assert search[0].node.metadata["source"] == "unit"


def test_rag_node_parser_uses_deterministic_chunk_ids():
    parser = build_rag_node_parser(chunk_size=64, chunk_overlap=8)

    assert isinstance(parser, SentenceSplitter)
    assert parser.id_func(0, Document(text="content", id_="doc-1")) == "doc-1:chunk:0"


async def test_index_empty_documents_returns_zero_counts(rag_service):
    result = await rag_service.index([])

    assert result == {"indexed_count": 0, "chunk_count": 0}


async def test_index_is_incremental(rag_service):
    await rag_service.index(
        [Document(id_="doc-1", text="first document content", metadata={})]
    )
    await rag_service.index(
        [Document(id_="doc-2", text="second document content", metadata={})]
    )

    search = await rag_service.search("document", top_k=5)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {"doc-1", "doc-2"}


async def test_delete_removes_document_chunks_from_index(rag_service):
    await rag_service.index(
        [
            Document(id_="doc-1", text="first document", metadata={}),
            Document(id_="doc-2", text="second document", metadata={}),
        ]
    )

    await rag_service.delete("doc-1")

    search = await rag_service.search("document", top_k=5)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {"doc-2"}


async def test_search_uses_metadata_filter_pre_retrieval(rag_service):
    await rag_service.index(
        [
            Document(id_="doc-a", text="alpha content", metadata={"tenant": "a"}),
            Document(id_="doc-b", text="alpha content", metadata={"tenant": "b"}),
        ]
    )

    search = await rag_service.search("alpha", top_k=5, filters={"tenant": "a"})

    tenants = {match.node.metadata["tenant"] for match in search}
    assert tenants == {"a"}


async def test_filter_values_are_data_not_sql(rag_service):
    await rag_service.index(
        [Document(id_="doc-a", text="alpha content", metadata={"tenant": "a"})]
    )

    injected = await rag_service.search(
        "alpha", top_k=5, filters={"tenant": "x' OR '1'='1"}
    )
    injected_key = await rag_service.search(
        "alpha", top_k=5, filters={"tenant'--": "a"}
    )

    assert injected == []
    assert injected_key == []


async def test_filters_match_non_string_metadata(rag_service):
    await rag_service.index(
        [
            Document(
                id_="doc-1", text="beta content", metadata={"rank": 1, "ok": True}
            ),
            Document(
                id_="doc-2", text="beta content", metadata={"rank": 2, "ok": False}
            ),
        ]
    )

    by_rank = await rag_service.search("beta", filters={"rank": 2})
    by_flag = await rag_service.search("beta", filters={"ok": True})

    assert {m.node.metadata["document_id"] for m in by_rank} == {"doc-2"}
    assert {m.node.metadata["document_id"] for m in by_flag} == {"doc-1"}


async def test_concurrent_index_calls_are_serialized(rag_service):
    async def index_doc(doc_id: str) -> None:
        await rag_service.index(
            [Document(id_=doc_id, text=f"content of {doc_id}", metadata={})]
        )

    await asyncio.gather(*(index_doc(f"doc-{i}") for i in range(5)))

    search = await rag_service.search("content", top_k=10)
    document_ids = {match.node.metadata["document_id"] for match in search}
    assert document_ids == {f"doc-{i}" for i in range(5)}


async def test_new_service_over_same_database_sees_indexed_documents(rag_settings):
    first = build_rag_service(rag_settings)
    try:
        await first.index(
            [Document(id_="doc-1", text="durable fact", metadata={"tenant": "a"})]
        )
    finally:
        await first.aclose()

    second = build_rag_service(rag_settings)
    try:
        found = await second.search("durable", top_k=5, filters={"tenant": "a"})
        assert [m.node.metadata["document_id"] for m in found] == ["doc-1"]
        await second.delete("doc-1")
    finally:
        await second.aclose()

    third = build_rag_service(rag_settings)
    try:
        assert await third.search("durable", top_k=5) == []
    finally:
        await third.aclose()


async def test_search_respects_retrieve_timeout(rag_settings):
    service = build_rag_service(
        rag_settings.model_copy(update={"RAG_RETRIEVE_TIMEOUT_SECONDS": 1e-9})
    )
    try:
        await service.index([Document(id_="doc-1", text="some content", metadata={})])
        with pytest.raises(asyncio.TimeoutError):
            await service.search("content")
    finally:
        await service.aclose()


async def test_build_rag_service_uses_settings_defaults(rag_service):
    assert isinstance(rag_service, KnowledgeRetrievalService)
    assert rag_service.default_top_k == 5
    assert rag_service.retrieve_timeout is not None


def test_rag_addon_respects_enabled_flag():
    addon = RagAddon()
    enabled = build_test_settings(RAG_ENABLED=True, DATABASE_ENABLED=True)

    assert addon.is_enabled(enabled) is True
    assert addon.is_enabled(build_test_settings()) is False


async def _app_connection_count(engine: AsyncEngine, database: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": database},
        )
        return int(result.scalar_one())


async def test_rag_addon_opens_service_and_closes_connections(
    rag_settings: Settings, pg_engine: AsyncEngine
):
    FastAPI()
    resources = ApplicationResources()

    stack = await open_addon(RagAddon(), resources, rag_settings)
    service = resources.rag_service
    assert isinstance(service, KnowledgeRetrievalService)
    await service.index([Document(id_="doc-1", text="held connection", metadata={})])
    await service.search("held")
    assert await _app_connection_count(pg_engine, rag_settings.POSTGRES_DB) > 0

    await stack.aclose()

    assert await _app_connection_count(pg_engine, rag_settings.POSTGRES_DB) == 0


def test_build_embed_model_raises_for_unimplemented_provider():
    with pytest.raises(RuntimeError, match="not implemented"):
        build_embed_model(
            build_test_settings(RAG_EMBED_MODEL="openai:text-embedding-3-small")
        )
