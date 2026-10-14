"""AI capability settings: LLM router, Langfuse observability, RAG."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AISettingsMixin(BaseModel):
    # LLM router
    CHAT_MODEL: str = ""
    CHAT_FALLBACK_MODELS: str = ""
    JUDGE_CHAT_MODEL: str = ""
    # Chat streaming backend for the gRPC ChatService (ML/LLM decoupling seam):
    # "mock" streams deterministic tokens offline; "llm_router" streams from the
    # external LLM via the existing router (team-ai embeds no model itself).
    CHAT_BACKEND: str = "mock"  # "mock" | "llm_router"

    # Langfuse observability
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_PROMPT_CACHE_TTL_SECONDS: int = Field(default=60, ge=0)

    # RAG
    RAG_ENABLED: bool = False
    # Vector store backend: "memory" (in-process, dev) | "qdrant" (real infra).
    RAG_BACKEND: str = "memory"
    RAG_CHUNK_SIZE: int = Field(default=512, gt=0)
    RAG_CHUNK_OVERLAP: int = Field(default=50, ge=0)
    RAG_DEFAULT_TOP_K: int = Field(default=5, gt=0)
    RAG_EMBED_MODEL: str = ""
    RAG_MOCK_EMBED_DIM: int = Field(default=16, gt=0)
    RAG_RETRIEVE_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)

    # Embedding backend — the ML/LLM decoupling seam. team-ai runs NO embedding
    # model in-process; "model_server" delegates vectorization to a remote ML
    # serving layer over HTTP. "mock" keeps deterministic dev vectors offline.
    RAG_EMBED_BACKEND: str = "mock"  # "mock" | "model_server"
    RAG_EMBED_SERVER_URL: str = ""  # base URL of the embedding/ML server
    RAG_EMBED_SERVER_PATH: str = "/embed"  # POST {"texts": [...]} -> vectors
    RAG_EMBED_DIM: int = Field(default=384, gt=0)  # vector dim from the server
    RAG_EMBED_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)

    # Qdrant vector store (used when RAG_BACKEND=qdrant).
    RAG_QDRANT_URL: str = "http://localhost:6333"
    RAG_QDRANT_COLLECTION: str = "rag_documents"
