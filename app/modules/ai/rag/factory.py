from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.redaction import RedactionPolicy
from app.core.resilience import TimeoutPolicy
from app.modules.ai._deps import require_llama_index

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding

    from app.modules.ai.rag.service import KnowledgeRetrievalService
    from app.modules.ai.rag.store import ParameterizedPGVectorStore

# LlamaIndex lives behind the [ai] extra: everything here imports it lazily so
# registering RagAddon (which happens on every boot) never pulls the package —
# only actually opening the addon (RAG_ENABLED=true) does.


def build_embed_model(settings: Settings) -> BaseEmbedding:
    require_llama_index()
    from llama_index.core.embeddings import MockEmbedding

    if not settings.RAG_EMBED_MODEL:
        return MockEmbedding(embed_dim=settings.RAG_MOCK_EMBED_DIM)

    raise RuntimeError(
        f"RAG_EMBED_MODEL={settings.RAG_EMBED_MODEL!r} not implemented. "
        "Extend build_embed_model() to wire your embedding provider."
    )


def build_vector_store(settings: Settings) -> ParameterizedPGVectorStore:
    require_llama_index()
    from sqlalchemy.engine import URL

    from app.modules.ai.rag.store import ParameterizedPGVectorStore

    # To add a vector store: extend RagBackend in app/core/config/ai.py and add
    # a case here; pyright fails the build until every backend is handled.
    match settings.RAG_BACKEND:
        case "pgvector":

            def dsn(driver: str) -> str:
                return URL.create(
                    f"postgresql+{driver}",
                    username=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    database=settings.POSTGRES_DB,
                ).render_as_string(hide_password=False)

            store = ParameterizedPGVectorStore(
                connection_string=dsn("psycopg2"),
                async_connection_string=dsn("asyncpg"),
                table_name=settings.RAG_PGVECTOR_TABLE,
                schema_name="public",
                hybrid_search=False,
                text_search_config="english",
                cache_ok=False,
                debug=False,
                hnsw_kwargs=None,
                embed_dim=settings.RAG_MOCK_EMBED_DIM,
                use_jsonb=True,
                perform_setup=True,
                initialization_fail_on_error=True,
                create_engine_kwargs={"pool_pre_ping": True},
            )
            store.setup()
            return store


def build_rag_service(settings: Settings) -> KnowledgeRetrievalService:
    require_llama_index()
    from app.modules.ai.rag.service import (
        KnowledgeRetrievalService,
        build_rag_node_parser,
    )

    return KnowledgeRetrievalService(
        embed_model=build_embed_model(settings),
        node_parser=build_rag_node_parser(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        ),
        redaction_policy=RedactionPolicy(mode="redacted"),
        vector_store=build_vector_store(settings),
        default_top_k=settings.RAG_DEFAULT_TOP_K,
        retrieve_timeout=TimeoutPolicy(
            timeout_seconds=settings.RAG_RETRIEVE_TIMEOUT_SECONDS
        ),
    )
