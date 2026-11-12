from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from loguru import logger

from app.api.router import build_api_router
from app.bootstrap.addons.base import BootstrapAddon, default_resource_addons
from app.bootstrap.features.base import Feature
from app.bootstrap.features.registry import FEATURES
from app.bootstrap.middleware import install_core_middlewares
from app.bootstrap.resources import ApplicationResources, build_health_service
from app.bootstrap.services import open_runtime
from app.bootstrap.state import get_in_flight_tracker
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.middleware import InFlightTracker
from app.core.telemetry import require_otel


def create_app(
    *,
    settings: Settings | None = None,
    features: tuple[Feature, ...] = FEATURES,
    init_resources: bool = True,
    resource_addons: tuple[BootstrapAddon, ...] = (),
) -> FastAPI:
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
            addons=addons,
            features=features,
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        default_response_class=ORJSONResponse,
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(check_external_dependencies=False)
    app.state.in_flight_tracker = (
        InFlightTracker() if resolved_settings.GRACEFUL_SHUTDOWN_ENABLED else None
    )
    app.state.resources = ApplicationResources()
    install_core_middlewares(app, resolved_settings)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings, features))
    if resolved_settings.OTEL_ENABLED:
        _instrument_fastapi(app)
    return app


def _build_lifespan(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
    features: tuple[Feature, ...],
):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if init_resources:
            logger.info("settings {}", settings.redacted_summary())
        async with open_runtime(
            settings,
            init_resources=init_resources,
            addons=addons,
            features=features,
        ) as resources:
            app.state.resources = resources
            health_service = build_health_service(
                resources,
                init_resources=init_resources,
            )
            app.state.health_service = health_service
            try:
                yield
            finally:
                health_service.begin_draining()
                await _drain_in_flight(app, settings.GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS)
        app.state.resources = ApplicationResources()
        app.state.health_service = HealthService(check_external_dependencies=False)

    return lifespan


async def _drain_in_flight(app: FastAPI, timeout_seconds: int) -> None:
    if timeout_seconds <= 0:
        return
    tracker = get_in_flight_tracker(app)
    if tracker is None:
        return
    await tracker.wait_idle(timeout=timeout_seconds)


def _instrument_fastapi(app: FastAPI) -> None:
    # Needs the app object, so it cannot live in the addon; the providers the
    # addon installs globally at startup are picked up lazily.
    require_otel()
    from app.core.telemetry_otel import instrument_fastapi

    instrument_fastapi(app)
