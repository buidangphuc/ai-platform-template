from functools import lru_cache

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
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
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = 0
    REDIS_TIMEOUT_SECONDS: int = 5

    AUTH_BEARER_TOKEN: str = ""
    AUTH_SUBJECT: str = "local-user"
    AUTH_ROLES: str = "admin"
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60
    IDEMPOTENCY_ENABLED: bool = False

    CHAT_MODEL: str = ""

    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_PROMPT_CACHE_TTL_SECONDS: int = 60

    CORS_ALLOW_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    TRUSTED_HOSTS: str = "*"
    MAX_REQUEST_BODY_BYTES: int = 10 * 1024 * 1024

    GZIP_ENABLED: bool = False
    GZIP_MIN_SIZE: int = 1024
    GZIP_COMPRESS_LEVEL: int = 5

    REQUEST_TIMEOUT_ENABLED: bool = False
    REQUEST_TIMEOUT_SECONDS: int = 30
    REQUEST_TIMEOUT_EXCLUDE_PATTERNS: str = "/stream,/sse"

    GRACEFUL_SHUTDOWN_ENABLED: bool = False
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: int = 30

    QUEUE_BACKEND: str = "memory"
    QUEUE_NAME: str = "completions"
    SQS_QUEUE_URL: str = ""
    SQS_REGION: str = "ap-southeast-1"
    RABBITMQ_URL: str = ""

    TASK_STORE_BACKEND: str = "memory"
    TASK_REDIS_PREFIX: str = "tasks"
    TASK_TTL_SECONDS: int = 86400

    WORKER_MAX_CONCURRENT: int = 10
    WORKER_POLL_INTERVAL_SECONDS: float = 0.5
    WORKER_RECEIVE_BATCH_SIZE: int = 10
    WORKER_RECEIVE_WAIT_SECONDS: float = 1.0

    DOCS_ENABLED: bool = True

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_ENQUEUE: bool = False

    @field_validator("DEFAULT_RATE_LIMIT_PER_MINUTE")
    @classmethod
    def validate_default_rate_limit_per_minute(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("DEFAULT_RATE_LIMIT_PER_MINUTE must be positive")
        return value

    @field_validator(
        "DB_POOL_SIZE", "DB_POOL_TIMEOUT_SECONDS", "DB_POOL_RECYCLE_SECONDS"
    )
    @classmethod
    def validate_db_pool_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("DB pool sizing values must be positive")
        return value

    @field_validator("DB_MAX_OVERFLOW")
    @classmethod
    def validate_db_max_overflow(cls, value: int) -> int:
        if value < 0:
            raise ValueError("DB_MAX_OVERFLOW must not be negative")
        return value

    @field_validator("LANGFUSE_PROMPT_CACHE_TTL_SECONDS")
    @classmethod
    def validate_langfuse_prompt_cache_ttl_seconds(cls, value: int) -> int:
        if value < 0:
            raise ValueError("LANGFUSE_PROMPT_CACHE_TTL_SECONDS must not be negative")
        return value

    @field_validator("MAX_REQUEST_BODY_BYTES")
    @classmethod
    def validate_max_request_body_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be positive")
        return value

    @field_validator("GZIP_MIN_SIZE")
    @classmethod
    def validate_gzip_min_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("GZIP_MIN_SIZE must not be negative")
        return value

    @field_validator("GZIP_COMPRESS_LEVEL")
    @classmethod
    def validate_gzip_compress_level(cls, value: int) -> int:
        if not 1 <= value <= 9:
            raise ValueError("GZIP_COMPRESS_LEVEL must be between 1 and 9")
        return value

    @field_validator("REQUEST_TIMEOUT_SECONDS")
    @classmethod
    def validate_request_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be positive")
        return value

    @field_validator("GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS")
    @classmethod
    def validate_graceful_shutdown_timeout_seconds(cls, value: int) -> int:
        if value < 0:
            raise ValueError("GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS must not be negative")
        return value

    @field_validator("QUEUE_BACKEND")
    @classmethod
    def validate_queue_backend(cls, value: str) -> str:
        allowed = {"memory", "redis", "sqs", "rabbitmq"}
        if value not in allowed:
            raise ValueError(f"QUEUE_BACKEND must be one of {sorted(allowed)}")
        return value

    @field_validator("TASK_STORE_BACKEND")
    @classmethod
    def validate_task_store_backend(cls, value: str) -> str:
        allowed = {"memory", "postgres", "redis"}
        if value not in allowed:
            raise ValueError(f"TASK_STORE_BACKEND must be one of {sorted(allowed)}")
        return value

    @field_validator("TASK_TTL_SECONDS")
    @classmethod
    def validate_task_ttl_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("TASK_TTL_SECONDS must be positive")
        return value

    @field_validator("WORKER_MAX_CONCURRENT", "WORKER_RECEIVE_BATCH_SIZE")
    @classmethod
    def validate_worker_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Worker concurrency values must be positive")
        return value

    @field_validator("WORKER_POLL_INTERVAL_SECONDS", "WORKER_RECEIVE_WAIT_SECONDS")
    @classmethod
    def validate_worker_non_negative_float(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Worker timing values must not be negative")
        return value

    @field_validator("CHAT_MODEL")
    @classmethod
    def validate_chat_model(cls, value: str) -> str:
        if value and not value.strip():
            raise ValueError("CHAT_MODEL must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_auth_token_for_non_local_runtime(self) -> "Settings":
        if (
            self.ENVIRONMENT.lower() not in {"dev", "local", "test"}
            and not self.AUTH_BEARER_TOKEN
        ):
            raise ValueError("AUTH_BEARER_TOKEN is required outside dev/local/test")
        return self

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def auth_roles(self) -> list[str]:
        return [role.strip() for role in self.AUTH_ROLES.split(",") if role.strip()]

    @computed_field
    @property
    def cors_allow_origins(self) -> list[str]:
        return self._split_csv(self.CORS_ALLOW_ORIGINS)

    @computed_field
    @property
    def trusted_hosts(self) -> list[str]:
        return self._split_csv(self.TRUSTED_HOSTS)

    @computed_field
    @property
    def request_timeout_exclude_patterns(self) -> list[str]:
        return self._split_csv(self.REQUEST_TIMEOUT_EXCLUDE_PATTERNS)

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

    def _split_csv(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
