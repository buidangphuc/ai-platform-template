"""Platform-layer settings: auth, rate limit, cache, objects, idempotency."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, computed_field, model_validator


class PlatformSettingsMixin(BaseModel):
    # Backing-service flags owned by the infra / mongo mixins; re-declared here
    # (same type and default) so the cross-setting rules below can read them.
    DATABASE_ENABLED: bool = False
    REDIS_ENABLED: bool = False
    MONGO_ENABLED: bool = False

    # Auth / identity
    AUTH_BEARER_TOKEN: str = ""
    AUTH_SUBJECT: str = "local-user"
    AUTH_ROLES: str = "admin"

    # Rate limit (2 layers: IP + principal)
    RATE_LIMIT_ENABLED: bool = False
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

    @model_validator(mode="after")
    def validate_backend_requirements(self) -> Self:
        """Each enabled feature's backend needs the service it runs on."""
        rules = (
            (
                self.RATE_LIMIT_ENABLED and self.RATE_LIMIT_BACKEND == "redis",
                self.REDIS_ENABLED,
                "RATE_LIMIT_BACKEND=redis requires REDIS_ENABLED",
            ),
            (
                self.CACHE_ENABLED and self.CACHE_BACKEND == "redis",
                self.REDIS_ENABLED,
                "CACHE_BACKEND=redis requires REDIS_ENABLED",
            ),
            (
                self.IDEMPOTENCY_ENABLED and self.IDEMPOTENCY_BACKEND == "postgres",
                self.DATABASE_ENABLED,
                "IDEMPOTENCY_BACKEND=postgres requires DATABASE_ENABLED",
            ),
            (
                self.QUOTA_ENABLED and self.QUOTA_BACKEND == "postgres",
                self.DATABASE_ENABLED,
                "QUOTA_BACKEND=postgres requires DATABASE_ENABLED",
            ),
            (
                self.QUOTA_ENABLED and self.QUOTA_BACKEND == "mongo",
                self.MONGO_ENABLED,
                "QUOTA_BACKEND=mongo requires MONGO_ENABLED",
            ),
            (
                self.OBJECTS_ENABLED and self.OBJECT_BACKEND == "s3",
                bool(self.OBJECT_S3_BUCKET),
                "OBJECT_BACKEND=s3 requires OBJECT_S3_BUCKET",
            ),
        )
        for applies, satisfied, message in rules:
            if applies and not satisfied:
                raise ValueError(message)
        return self

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
