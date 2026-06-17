"""Runtime / process-lifecycle settings: environment, project metadata, logging,
graceful shutdown, docs toggle."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

WEAK_AUTH_TOKENS = frozenset(
    {
        "change-me-local-bearer-token",
        "test-token",
        "local-token",
        "dev-token",
    }
)


class Environment(StrEnum):
    DEV = "dev"
    LOCAL = "local"
    TEST = "test"
    PROD = "prod"
    PRODUCTION = "production"

    @property
    def is_local(self) -> bool:
        return self in {Environment.DEV, Environment.LOCAL, Environment.TEST}

    @property
    def is_production(self) -> bool:
        return self in {Environment.PROD, Environment.PRODUCTION}


class RuntimeSettingsMixin(BaseModel):
    ENVIRONMENT: Environment = Environment.DEV
    PROJECT_NAME: str = "AI Solution Engineering Platform"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Reusable FastAPI foundation for AI solution engineering"
    API_V1_PREFIX: str = "/api/v1"

    DOCS_ENABLED: bool = True

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_ENQUEUE: bool = False

    GRACEFUL_SHUTDOWN_ENABLED: bool = False
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: int = Field(default=30, ge=0)

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        # Accept any case from env vars / .env files.
        if isinstance(value, str):
            return value.lower()
        return value
