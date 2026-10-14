from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.redaction import RedactionPolicy
from app.core.resilience import TimeoutPolicy
from app.modules.ai._deps import require_llama_index

if TYPE_CHECKING:
    from llama_index.core import StorageContext
    from llama_index.core.base.embeddings.base import BaseEmbedding

    from app.modules.ai.rag.service import KnowledgeRetrievalService

# LlamaIndex lives behind the [ai] extra: everything here imports it lazily so
# registering RagAddon (which happens on every boot) never pulls the package —
# only actually opening the addon (RAG_ENABLED=true) does.


def build_embed_model(settings: Settings) -> BaseEmbedding:
    """Select the embedding backend.

    ``mock`` keeps deterministic in-process vectors for offline dev. ``model_server``
    is the ML/LLM decoupling seam: vectorization is delegated to a remote ML serving
    layer over HTTP, so team-ai carries no embedding model itself. The returned
    object may own network clients — the caller closes it via ``aclose()``.
    """
    require_llama_index()

    if settings.RAG_EMBED_BACKEND == "mock":
        from llama_index.core.embeddings import MockEmbedding

        return MockEmbedding(embed_dim=settings.RAG_MOCK_EMBED_DIM)

    if settings.RAG_EMBED_BACKEND == "model_server":
        from app.modules.ai.rag.embeddings import build_model_server_embedding

        return build_model_server_embedding(
            base_url=settings.RAG_EMBED_SERVER_URL,
            path=settings.RAG_EMBED_SERVER_PATH,
            embed_dim=settings.RAG_EMBED_DIM,
            timeout=settings.RAG_EMBED_TIMEOUT_SECONDS,
        )

    raise RuntimeError(
        f"RAG_EMBED_BACKEND={settings.RAG_EMBED_BACKEND!r} not supported "
        "(use 'mock' or 'model_server')."
    )


def build_storage_context(settings: Settings) -> StorageContext:
    require_llama_index()
    from llama_index.core import StorageContext

    if settings.RAG_BACKEND == "memory":
        return StorageContext.from_defaults()

    if settings.RAG_BACKEND == "qdrant":
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.RAG_QDRANT_URL)
        vector_store = QdrantVectorStore(
            client=client,
            collection_name=settings.RAG_QDRANT_COLLECTION,
        )
        return StorageContext.from_defaults(vector_store=vector_store)

    raise RuntimeError(
        f"RAG_BACKEND={settings.RAG_BACKEND!r} not supported "
        "(use 'memory' or 'qdrant')."
    )


def build_rag_service(
    settings: Settings,
    *,
    embed_model: BaseEmbedding,
) -> KnowledgeRetrievalService:
    require_llama_index()
    from app.modules.ai.rag.service import (
        KnowledgeRetrievalService,
        build_rag_node_parser,
    )

    return KnowledgeRetrievalService(
        embed_model=embed_model,
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

    def __init__(self) -> None:
        self._embed_model: BaseEmbedding | None = None

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RAG_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        # Build the embedding first and keep a reference so its network clients
        # (model_server backend) are closed at shutdown.
        self._embed_model = build_embed_model(settings)
        resources.rag_service = build_rag_service(
            settings, embed_model=self._embed_model
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        resources.rag_service = None
        aclose = getattr(self._embed_model, "aclose", None)
        if aclose is not None:
            await aclose()
        self._embed_model = None
