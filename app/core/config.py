from functools import lru_cache
from typing import Literal

from pydantic import computed_field
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
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60

    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    TRACE_CONTENT: Literal["off", "redacted", "full"] = "redacted"

    OPENAI_API_KEY: str = ""
    LLM_PROVIDER: str = "fake"
    EMBEDDING_PROVIDER: str = "fake"
    VECTOR_STORE: str = "in_memory"
    STORAGE_BACKEND: str = "local"
    JOB_BACKEND: str = "in_process"

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
        secret_names = {
            "POSTGRES_PASSWORD",
            "POSTGRES_URL",
            "REDIS_PASSWORD",
            "API_KEY_PEPPER",
            "OPENAI_API_KEY",
        }
        return {
            key: "***" if key in secret_names and values.get(key) else value
            for key, value in values.items()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
