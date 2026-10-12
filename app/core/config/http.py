"""HTTP request/response middleware settings: CORS, trusted hosts, body limit,
security headers, gzip, request timeout."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class HttpSettingsMixin(BaseModel):
    CORS_ALLOW_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    TRUSTED_HOSTS: str = "*"
    MAX_REQUEST_BODY_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)

    SECURITY_HEADERS_ENABLED: bool = False
    SECURITY_HSTS_ENABLED: bool = False
    SECURITY_HSTS_MAX_AGE_SECONDS: int = Field(default=31_536_000, ge=0)

    GZIP_ENABLED: bool = False
    GZIP_MIN_SIZE: int = Field(default=1024, ge=0)
    GZIP_COMPRESS_LEVEL: int = Field(default=5, ge=1, le=9)

    REQUEST_TIMEOUT_ENABLED: bool = False
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    REQUEST_TIMEOUT_EXCLUDE_PATTERNS: str = "/stream,/sse"

    # Server-sent events (completions stream). The heartbeat keeps proxies from
    # closing an idle connection; the deadlines bound how long a stream may wait
    # on the model: before the first chunk (JSON 504) and between chunks (an
    # ``event: error`` with code ``stream_timeout``).
    SSE_HEARTBEAT_SECONDS: float = Field(default=15, gt=0)
    STREAM_FIRST_TOKEN_TIMEOUT_SECONDS: float = Field(default=30, gt=0)
    STREAM_IDLE_TIMEOUT_SECONDS: float = Field(default=30, gt=0)

    # Upper bound for each readiness dependency check; checks run concurrently,
    # so the probe takes at most about this long however many are registered.
    HEALTH_CHECK_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)

    # Reverse proxies in front of the app that append to X-Forwarded-For. 0 = do
    # not trust the header; the per-IP rate limit keys on the socket peer.
    TRUSTED_PROXY_COUNT: int = Field(default=0, ge=0)

    @computed_field
    @property
    def cors_allow_origins(self) -> list[str]:
        return [v.strip() for v in self.CORS_ALLOW_ORIGINS.split(",") if v.strip()]

    @computed_field
    @property
    def trusted_hosts(self) -> list[str]:
        return [v.strip() for v in self.TRUSTED_HOSTS.split(",") if v.strip()]

    @computed_field
    @property
    def request_timeout_exclude_patterns(self) -> list[str]:
        return [
            v.strip()
            for v in self.REQUEST_TIMEOUT_EXCLUDE_PATTERNS.split(",")
            if v.strip()
        ]
