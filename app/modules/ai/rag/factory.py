from __future__ import annotations

from fastapi import FastAPI
from llama_index.core import StorageContext
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.embeddings import MockEmbedding

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.redaction import RedactionPolicy
from app.core.resilience import TimeoutPolicy
from app.modules.ai.rag.service import (
    KnowledgeRetrievalService,
    build_rag_node_parser,
)


def build_embed_model(settings: Settings) -> BaseEmbedding:
    if not settings.RAG_EMBED_MODEL:
        return MockEmbedding(embed_dim=settings.RAG_MOCK_EMBED_DIM)

    raise RuntimeError(
        f"RAG_EMBED_MODEL={settings.RAG_EMBED_MODEL!r} not implemented. "
        "Extend build_embed_model() to wire your embedding provider."
    )


def build_storage_context(settings: Settings) -> StorageContext:
    if settings.RAG_BACKEND == "memory":
        return StorageContext.from_defaults()

    raise RuntimeError(
        f"RAG_BACKEND={settings.RAG_BACKEND!r} not implemented. "
        "Extend build_storage_context() with your vector store."
    )


def build_rag_service(settings: Settings) -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        embed_model=build_embed_model(settings),
        node_parser=build_rag_node_parser(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        ),
        redaction_policy=RedactionPolicy(mode="redacted"),
        storage_context=build_storage_context(settings),
        default_top_k=settings.RAG_DEFAULT_TOP_K,
        retrieve_timeout=TimeoutPolicy(
            timeout_seconds=settings.RAG_RETRIEVE_TIMEOUT_SECONDS
        ),
    )


class RagAddon:
    name = "rag"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RAG_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.rag_service = build_rag_service(settings)

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        resources.rag_service = None
