from functools import lru_cache
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "dev"
    PROJECT_NAME: str = "AI Solution Engineering Platform"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Reusable FastAPI foundation for AI solution engineering"
    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = 0
    REDIS_TIMEOUT_SECONDS: int = 5

    API_KEY_PEPPER: str
    API_KEY_BOOTSTRAP_TOKEN: str = ""
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60

    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    TRACE_CONTENT: Literal["off", "redacted", "full"] = "redacted"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_PROVIDER: Literal["fake", "openai_compatible"] = "fake"
    LLM_MODEL: str = "fake-chat"
    EMBEDDING_PROVIDER: Literal["fake", "openai_compatible"] = "fake"
    EMBEDDING_MODEL: str = "fake-embedding"
    FAKE_EMBEDDING_DIMENSIONS: int = 16
    VECTOR_STORE: Literal["in_memory"] = "in_memory"
    STORAGE_BACKEND: Literal["local"] = "local"
    LOCAL_STORAGE_ROOT: str = ".local/storage"
    JOB_BACKEND: Literal["in_process"] = "in_process"
    OBSERVABILITY_BACKEND: Literal["debug"] = "debug"
    LLM_CACHE_BACKEND: Literal["noop"] = "noop"
    LLM_CACHE_ENABLED: bool = False
    AGENT_RUNTIME: Literal["simple", "langgraph"] = "simple"
    RAG_CHUNK_SIZE: int = 512
    RAG_CHUNK_OVERLAP: int = 64
    EXPERIMENT_TRACKER_BACKEND: Literal["local", "mlflow"] = "local"
    LOCAL_EXPERIMENT_TRACKER_ROOT: str = "research/experiments/local"
    MLFLOW_TRACKING_URI: str = "file:./research/experiments/mlruns"
    MLFLOW_EXPERIMENT_NAME: str = "ai-platform-template"

    @field_validator("DEFAULT_RATE_LIMIT_PER_MINUTE")
    @classmethod
    def validate_default_rate_limit_per_minute(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("DEFAULT_RATE_LIMIT_PER_MINUTE must be positive")
        return value

    @field_validator("FAKE_EMBEDDING_DIMENSIONS")
    @classmethod
    def validate_fake_embedding_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("FAKE_EMBEDDING_DIMENSIONS must be positive")
        return value

    @field_validator("RAG_CHUNK_SIZE")
    @classmethod
    def validate_rag_chunk_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("RAG_CHUNK_SIZE must be positive")
        return value

    @field_validator("RAG_CHUNK_OVERLAP")
    @classmethod
    def validate_rag_chunk_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("RAG_CHUNK_OVERLAP must be non-negative")
        return value

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def redacted_summary(self) -> dict[str, object]:
        values = self.model_dump(mode="json")
        return {key: self._redacted_value(key, value) for key, value in values.items()}

    def _redacted_value(self, key: str, value: object) -> object:
        visible_names = {
            "LLM_PROVIDER",
            "EMBEDDING_PROVIDER",
            "VECTOR_STORE",
            "STORAGE_BACKEND",
            "JOB_BACKEND",
            "OBSERVABILITY_BACKEND",
            "LLM_CACHE_BACKEND",
            "AGENT_RUNTIME",
            "EXPERIMENT_TRACKER_BACKEND",
        }
        if key in visible_names or not value:
            return value

        key_upper = key.upper()
        secret_markers = ("PASSWORD", "SECRET", "TOKEN", "KEY", "PEPPER")
        if any(marker in key_upper for marker in secret_markers):
            return "***"

        if (
            key_upper.endswith("_URL")
            and isinstance(value, str)
            and "://" in value
            and "@" in value
        ):
            return "***"

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
