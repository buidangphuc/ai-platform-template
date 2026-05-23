from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.bootstrap.state import get_in_flight_tracker
from app.core.config import Settings
from app.core.middleware import (
    AccessLogMiddleware,
    InFlightTrackerMiddleware,
    IPRateLimitMiddleware,
    RequestBodyLimitMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.request_context import RequestIdMiddleware


def install_core_middlewares(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )
    app.add_middleware(AccessLogMiddleware)
    in_flight_tracker = get_in_flight_tracker(app)
    if in_flight_tracker is not None:
        app.add_middleware(
            InFlightTrackerMiddleware,
            tracker=in_flight_tracker,
        )
    if settings.GZIP_ENABLED:
        app.add_middleware(
            GZipMiddleware,
            minimum_size=settings.GZIP_MIN_SIZE,
            compresslevel=settings.GZIP_COMPRESS_LEVEL,
        )
    if settings.REQUEST_TIMEOUT_ENABLED:
        app.add_middleware(
            RequestTimeoutMiddleware,
            timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS,
            exclude_patterns=tuple(settings.request_timeout_exclude_patterns),
        )
    if settings.SECURITY_HEADERS_ENABLED:
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_enabled=settings.SECURITY_HSTS_ENABLED,
            hsts_max_age_seconds=settings.SECURITY_HSTS_MAX_AGE_SECONDS,
        )
    if settings.RATE_LIMIT_ENABLED and settings.RATE_LIMIT_IP_ENABLED:
        app.add_middleware(
            IPRateLimitMiddleware,
            exclude_patterns=tuple(settings.rate_limit_exclude_patterns),
        )
    app.add_middleware(RequestIdMiddleware)
