"""AI capability settings: LLM router, Langfuse observability, RAG."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RagBackend = Literal["pgvector"]
RagEmbedBackend = Literal["mock", "model_server"]


class AISettingsMixin(BaseModel):
    DATABASE_ENABLED: bool

    # LLM router
    LLM_ENABLED: bool = False
    CHAT_MODEL: str = ""
    CHAT_FALLBACK_MODELS: str = ""
    JUDGE_CHAT_MODEL: str = ""
    # Every provider call is bounded: output cap, per-request timeout and the
    # SDK's own hidden retry budget. LLM_MAX_RETRIES is kept at 1 because the
    # breaker only sees a call after the SDK has exhausted its retries, so each
    # extra retry multiplies the latency before failover can engage.
    LLM_MAX_TOKENS: int = Field(default=2048, gt=0, le=200_000)
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=600)
    LLM_MAX_RETRIES: int = Field(default=1, ge=0, le=5)
    # Overall budget for one ``LLMInstance.ainvoke`` across the whole fallback
    # chain; without it a 3-model chain can cost 3x LLM_TIMEOUT_SECONDS. It must
    # cover one target's full retry budget, LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES
    # + 1), or a hung primary eats the whole chain before the fallback is tried.
    LLM_CHAIN_DEADLINE_SECONDS: float = Field(default=90.0, gt=0, le=1800)
    # Primary-model circuit breaker: consecutive transient failures (429, 5xx,
    # timeouts, connection errors) before failover, and the cooldown before the
    # primary is probed again.
    LLM_BREAKER_FAILURE_THRESHOLD: int = Field(default=3, gt=0)
    LLM_BREAKER_COOLDOWN_SECONDS: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _chain_deadline_covers_the_retry_budget(self) -> AISettingsMixin:
        budget = self.LLM_TIMEOUT_SECONDS * (self.LLM_MAX_RETRIES + 1)
        if budget > self.LLM_CHAIN_DEADLINE_SECONDS:
            raise ValueError(
                "LLM_CHAIN_DEADLINE_SECONDS must be >= LLM_TIMEOUT_SECONDS * "
                f"(LLM_MAX_RETRIES + 1) = {budget:g}, "
                f"got {self.LLM_CHAIN_DEADLINE_SECONDS:g}"
            )
        return self

    # Langfuse observability
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_PROMPT_CACHE_TTL_SECONDS: int = Field(default=60, ge=0)

    # RAG
    RAG_ENABLED: bool = False
    RAG_BACKEND: RagBackend = "pgvector"
    RAG_PGVECTOR_TABLE: str = Field(
        default="rag_chunks", pattern=r"^[a-z_][a-z0-9_]{0,47}$"
    )
    RAG_CHUNK_SIZE: int = Field(default=512, gt=0)
    RAG_CHUNK_OVERLAP: int = Field(default=50, ge=0)
    RAG_DEFAULT_TOP_K: int = Field(default=5, gt=0)
    RAG_EMBED_BACKEND: RagEmbedBackend = "mock"
    RAG_EMBED_DIM: int = Field(default=16, gt=0)
    RAG_EMBED_SERVER_URL: str = ""
    RAG_EMBED_SERVER_PATH: str = "/embed"
    RAG_EMBED_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    RAG_EMBED_RETRIES: int = Field(default=1, ge=0, le=5)
    RAG_RETRIEVE_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _rag_backend_requirements(self) -> AISettingsMixin:
        if (
            self.RAG_ENABLED
            and self.RAG_BACKEND == "pgvector"
            and not self.DATABASE_ENABLED
        ):
            raise ValueError("RAG_ENABLED requires DATABASE_ENABLED")
        if (
            self.RAG_ENABLED
            and self.RAG_EMBED_BACKEND == "model_server"
            and not self.RAG_EMBED_SERVER_URL
        ):
            raise ValueError(
                "RAG_EMBED_BACKEND=model_server requires RAG_EMBED_SERVER_URL"
            )
        return self
