"""Platform-layer settings: auth, rate limit, cache, objects, idempotency."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class PlatformSettingsMixin(BaseModel):
    # Auth / identity
    AUTH_BEARER_TOKEN: str = ""
    AUTH_SUBJECT: str = "local-user"
    AUTH_ROLES: str = "admin"

    # Rate limit (2 layers: IP + principal)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_BACKEND: str = "memory"
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    RATE_LIMIT_REDIS_PREFIX: str = "rate-limit"
    RATE_LIMIT_IP_ENABLED: bool = True
    RATE_LIMIT_IP_PER_MINUTE: int = Field(default=600, gt=0)
    RATE_LIMIT_PRINCIPAL_ENABLED: bool = True
    RATE_LIMIT_PRINCIPAL_PER_MINUTE: int = Field(default=60, gt=0)
    RATE_LIMIT_EXCLUDE_PATHS: str = "/healthz,/readyz"

    # Cache
    CACHE_ENABLED: bool = False
    CACHE_BACKEND: str = "memory"
    CACHE_PREFIX: str = "app"
    CACHE_DEFAULT_TTL_SECONDS: float = Field(default=300, gt=0)

    # Object storage
    OBJECTS_ENABLED: bool = False
    OBJECT_BACKEND: str = "memory"
    OBJECT_PREFIX: str = "app"
    OBJECT_S3_BUCKET: str = ""
    OBJECT_S3_REGION: str = "ap-southeast-1"
    OBJECT_S3_ENDPOINT_URL: str = ""

    # Idempotency (sync endpoints only)
    IDEMPOTENCY_ENABLED: bool = False
    IDEMPOTENCY_BACKEND: str = "postgres"
    IDEMPOTENCY_TTL_SECONDS: int = Field(default=86_400, gt=0)
    IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS: int = Field(default=60, gt=0)
    IDEMPOTENCY_KEY_MAX_LENGTH: int = Field(default=64, gt=0)

    # Durable quota / entitlement counters
    QUOTA_ENABLED: bool = False
    QUOTA_BACKEND: str = "memory"

    @computed_field
    @property
    def auth_roles(self) -> list[str]:
        return [v.strip() for v in self.AUTH_ROLES.split(",") if v.strip()]

    @computed_field
    @property
    def rate_limit_exclude_patterns(self) -> list[str]:
        return [
            v.strip() for v in self.RATE_LIMIT_EXCLUDE_PATHS.split(",") if v.strip()
        ]
