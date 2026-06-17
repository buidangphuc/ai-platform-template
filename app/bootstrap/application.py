import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.api.router import build_api_router
from app.bootstrap.addons import BootstrapAddon, default_resource_addons
from app.bootstrap.middleware import install_core_middlewares
from app.bootstrap.resources import (
    ApplicationResources,
    close_application_resources,
    open_application_resources,
)
from app.bootstrap.state import get_in_flight_tracker
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.middleware import InFlightTracker
from app.modules.business.completions.pipeline import CompletionPipeline
from app.modules.business.completions.ports import CompletionHandler


def create_app(
    *,
    settings: Settings | None = None,
    completion_handler: CompletionHandler | None = None,
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
    resources = ApplicationResources()
    if completion_handler is not None:
        resources.completion_pipeline = CompletionPipeline(completion_handler)
    app.state.resources = resources
    install_core_middlewares(app, resolved_settings)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app


def _build_lifespan(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
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


async def _drain_in_flight(app: FastAPI, timeout_seconds: int) -> None:
    if timeout_seconds <= 0:
        return
    tracker = get_in_flight_tracker(app)
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
