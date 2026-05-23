"""AI capability settings: LLM router, Langfuse observability, RAG."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AISettingsMixin(BaseModel):
    # LLM router
    CHAT_MODEL: str = ""
    CHAT_FALLBACK_MODELS: str = ""
    JUDGE_CHAT_MODEL: str = ""

    # Langfuse observability
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_PROMPT_CACHE_TTL_SECONDS: int = Field(default=60, ge=0)

    # RAG
    RAG_ENABLED: bool = False
    RAG_BACKEND: str = "memory"
    RAG_CHUNK_SIZE: int = Field(default=512, gt=0)
    RAG_CHUNK_OVERLAP: int = Field(default=50, ge=0)
    RAG_DEFAULT_TOP_K: int = Field(default=5, gt=0)
    RAG_EMBED_MODEL: str = ""
    RAG_MOCK_EMBED_DIM: int = Field(default=16, gt=0)
    RAG_RETRIEVE_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
