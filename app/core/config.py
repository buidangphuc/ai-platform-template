from functools import lru_cache
from typing import Literal

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ChatProvider = Literal["", "anthropic", "openai", "google_genai"]

ChatModelName = Literal[
    "",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-7",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

CHAT_MODELS_BY_PROVIDER: dict[str, frozenset[str]] = {
    "anthropic": frozenset(
        {"claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-7"}
    ),
    "openai": frozenset({"gpt-4.1", "gpt-4.1-mini"}),
    "google_genai": frozenset({"gemini-1.5-pro", "gemini-1.5-flash"}),
}


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

    CHAT_PROVIDER: ChatProvider = ""
    CHAT_MODEL_NAME: ChatModelName = ""

    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_PROMPT_CACHE_TTL_SECONDS: int = 60

    @field_validator("DEFAULT_RATE_LIMIT_PER_MINUTE")
    @classmethod
    def validate_default_rate_limit_per_minute(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("DEFAULT_RATE_LIMIT_PER_MINUTE must be positive")
        return value

    @field_validator("LANGFUSE_PROMPT_CACHE_TTL_SECONDS")
    @classmethod
    def validate_langfuse_prompt_cache_ttl_seconds(cls, value: int) -> int:
        if value < 0:
            raise ValueError("LANGFUSE_PROMPT_CACHE_TTL_SECONDS must not be negative")
        return value

    @model_validator(mode="after")
    def validate_chat_model_pair(self) -> "Settings":
        if bool(self.CHAT_PROVIDER) != bool(self.CHAT_MODEL_NAME):
            raise ValueError(
                "CHAT_PROVIDER and CHAT_MODEL_NAME must both be set or both empty"
            )
        if self.CHAT_PROVIDER:
            allowed = CHAT_MODELS_BY_PROVIDER[self.CHAT_PROVIDER]
            if self.CHAT_MODEL_NAME not in allowed:
                raise ValueError(
                    f"CHAT_MODEL_NAME={self.CHAT_MODEL_NAME!r} is not supported "
                    f"for CHAT_PROVIDER={self.CHAT_PROVIDER!r}. "
                    f"Allowed: {sorted(allowed)}"
                )
        return self

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
        if not value:
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
