"""Platform-layer settings: auth, rate limit, cache, objects, idempotency."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Self

from pydantic import BaseModel, Field, computed_field, model_validator

RateLimitBackend = Literal["memory", "redis"]
CacheBackend = Literal["memory", "redis"]
ObjectBackend = Literal["memory", "s3"]
IdempotencyBackend = Literal["postgres"]
QuotaBackend = Literal["memory", "postgres", "mongo"]


@dataclass(frozen=True)
class ApiKey:
    """One configured API key: who it authenticates as and the SHA-256 of the token."""

    subject: str
    scopes: tuple[str, ...]
    digest: bytes


@lru_cache(maxsize=8)
def parse_api_keys(raw: str) -> tuple[ApiKey, ...]:
    """Parse ``AUTH_API_KEYS``: comma-separated ``subject:scope|scope:sha256hex``.

    The subject is everything before the first ``:``, the digest everything after
    the last one, so scopes may themselves contain ``:`` (``tasks:read``).
    Cached by the raw string, so a ``model_copy`` with new keys never goes stale.
    """
    keys: list[ApiKey] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        fields = entry.split(":")
        subject, scopes_part, digest_hex = fields[0], ":".join(fields[1:-1]), fields[-1]
        try:
            digest = bytes.fromhex(digest_hex)
        except ValueError:
            digest = b""
        if len(fields) < 3 or not subject.strip() or len(digest) != 32:
            raise ValueError(
                "AUTH_API_KEYS entries must look like "
                "'subject:scope|scope:sha256hex' (64 hex chars; scopes may be empty)"
            )
        scopes = tuple(s.strip() for s in scopes_part.split("|") if s.strip())
        keys.append(ApiKey(subject=subject.strip(), scopes=scopes, digest=digest))
    return tuple(keys)


class PlatformSettingsMixin(BaseModel):
    # Backing-service flags owned by the infra / mongo mixins; re-declared here
    # (same type and default) so the cross-setting rules below can read them.
    DATABASE_ENABLED: bool = False
    REDIS_ENABLED: bool = False
    MONGO_ENABLED: bool = False

    # Auth / identity
    # Comma-separated ``subject:scope|scope:sha256hex`` entries (see parse_api_keys).
    # Several entries may share a subject (overlap rotation). Hash tokens with
    # ``python -m scripts.hash_api_key``.
    AUTH_API_KEYS: str = ""

    # Rate limit (2 layers: IP + principal)
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_BACKEND: RateLimitBackend = "memory"
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    RATE_LIMIT_REDIS_PREFIX: str = "rate-limit"
    RATE_LIMIT_IP_ENABLED: bool = True
    RATE_LIMIT_IP_PER_MINUTE: int = Field(default=600, gt=0)
    RATE_LIMIT_PRINCIPAL_ENABLED: bool = True
    RATE_LIMIT_PRINCIPAL_PER_MINUTE: int = Field(default=60, gt=0)
    RATE_LIMIT_EXCLUDE_PATHS: str = "/healthz,/readyz"

    # Cache
    CACHE_ENABLED: bool = False
    CACHE_BACKEND: CacheBackend = "memory"
    CACHE_PREFIX: str = "app"
    CACHE_DEFAULT_TTL_SECONDS: float = Field(default=300, gt=0)

    # Object storage
    OBJECTS_ENABLED: bool = False
    OBJECT_BACKEND: ObjectBackend = "memory"
    OBJECT_PREFIX: str = "app"
    OBJECT_S3_BUCKET: str = ""
    OBJECT_S3_REGION: str = "ap-southeast-1"
    OBJECT_S3_ENDPOINT_URL: str = ""

    # Idempotency (sync endpoints only)
    IDEMPOTENCY_ENABLED: bool = False
    IDEMPOTENCY_BACKEND: IdempotencyBackend = "postgres"
    IDEMPOTENCY_TTL_SECONDS: int = Field(default=86_400, gt=0)
    # Must exceed the slowest handler (LLM calls can take minutes): an
    # in-progress record older than this is reclaimed and the handler re-runs.
    # The age is measured from the claim, it is never refreshed.
    IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS: int = Field(default=600, gt=0)
    IDEMPOTENCY_KEY_MAX_LENGTH: int = Field(default=64, gt=0)

    # Durable quota / entitlement counters
    QUOTA_ENABLED: bool = False
    QUOTA_BACKEND: QuotaBackend = "memory"

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

    @model_validator(mode="after")
    def _validate_api_keys(self) -> Self:
        parse_api_keys(self.AUTH_API_KEYS)  # a bad entry fails at boot
        return self

    @property
    def auth_api_keys(self) -> tuple[ApiKey, ...]:
        return parse_api_keys(self.AUTH_API_KEYS)

    @computed_field
    @property
    def rate_limit_exclude_patterns(self) -> list[str]:
        return [
            v.strip() for v in self.RATE_LIMIT_EXCLUDE_PATHS.split(",") if v.strip()
        ]
