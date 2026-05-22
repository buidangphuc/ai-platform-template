import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import build_api_router
from app.api.v1.completions.handler import CompletionHandler
from app.bootstrap.addons import BootstrapAddon, default_resource_addons
from app.bootstrap.manifest import build_bootstrap_manifest
from app.bootstrap.resources import (
    close_application_resources,
    open_application_resources,
)
from app.bootstrap.state import optional_app_resource
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.middleware import (
    AccessLogMiddleware,
    InFlightTracker,
    InFlightTrackerMiddleware,
    RequestBodyLimitMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.request_context import RequestIdMiddleware


def create_app(
    completion_handler: CompletionHandler | Settings | None = None,
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
    resource_addons: tuple[BootstrapAddon, ...] = (),
) -> FastAPI:
    if isinstance(completion_handler, Settings):
        if settings is not None:
            raise TypeError("settings cannot be provided twice")
        settings = completion_handler
        completion_handler = None
    resolved_settings = settings or get_settings()
    configure_logging(
        level=resolved_settings.LOG_LEVEL,
        json_mode=resolved_settings.LOG_JSON,
        enqueue=resolved_settings.LOG_ENQUEUE,
    )
    docs_url = "/docs" if resolved_settings.DOCS_ENABLED else None
    redoc_url = "/redoc" if resolved_settings.DOCS_ENABLED else None
    openapi_url = "/openapi.json" if resolved_settings.DOCS_ENABLED else None
    addons = (*default_resource_addons(), *resource_addons)
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
        lifespan=_build_lifespan(
            resolved_settings,
            init_resources=init_resources,
            resource_addons=resource_addons,
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        default_response_class=ORJSONResponse,
    )
    app.state.settings = resolved_settings
    app.state.completion_handler = completion_handler
    app.state.bootstrap_manifest = build_bootstrap_manifest(
        settings=resolved_settings,
        init_resources=init_resources,
        addons=addons,
    )
    app.state.health_service = HealthService(check_external_dependencies=False)
    app.state.in_flight_tracker = (
        InFlightTracker() if resolved_settings.GRACEFUL_SHUTDOWN_ENABLED else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allow_origins,
        allow_credentials=resolved_settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.trusted_hosts,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=resolved_settings.MAX_REQUEST_BODY_BYTES,
    )
    app.add_middleware(AccessLogMiddleware)
    if app.state.in_flight_tracker is not None:
        app.add_middleware(
            InFlightTrackerMiddleware, tracker=app.state.in_flight_tracker
        )
    if resolved_settings.GZIP_ENABLED:
        app.add_middleware(
            GZipMiddleware,
            minimum_size=resolved_settings.GZIP_MIN_SIZE,
            compresslevel=resolved_settings.GZIP_COMPRESS_LEVEL,
        )
    if resolved_settings.REQUEST_TIMEOUT_ENABLED:
        app.add_middleware(
            RequestTimeoutMiddleware,
            timeout_seconds=resolved_settings.REQUEST_TIMEOUT_SECONDS,
            exclude_patterns=tuple(resolved_settings.request_timeout_exclude_patterns),
        )
    if resolved_settings.SECURITY_HEADERS_ENABLED:
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_enabled=resolved_settings.SECURITY_HSTS_ENABLED,
            hsts_max_age_seconds=resolved_settings.SECURITY_HSTS_MAX_AGE_SECONDS,
        )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app


def _build_lifespan(
    settings: Settings,
    *,
    init_resources: bool,
    resource_addons: tuple[BootstrapAddon, ...] = (),
):
    addons = (*default_resource_addons(), *resource_addons)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            if app is not None:
                await open_application_resources(
                    app,
                    settings,
                    init_resources=init_resources,
                    addons=addons,
                )
            yield
        finally:
            await _drain_in_flight(app, settings.GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS)
            if init_resources and settings.LANGFUSE_ENABLED:
                await asyncio.to_thread(_flush_langfuse_client)
            await close_application_resources(app)

    return lifespan


async def _drain_in_flight(app: FastAPI | None, timeout_seconds: int) -> None:
    if app is None or timeout_seconds <= 0:
        return
    tracker = optional_app_resource(app, "in_flight_tracker")
    if tracker is None:
        return
    await tracker.wait_idle(timeout=timeout_seconds)


def _flush_langfuse_client() -> None:
    try:
        from langfuse import get_client
    except ImportError:
        return
    client = get_client()
    if client is not None and hasattr(client, "flush"):
        client.flush()
