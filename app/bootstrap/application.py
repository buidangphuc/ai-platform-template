from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.database import check_postgres_connection
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.redis import check_redis_connection
from app.core.request_context import RequestIdMiddleware
from app.modules.identity.repository import ApiKeyRepository
from app.modules.rate_limit.service import InMemoryRateLimiter


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
        lifespan=_build_lifespan(resolved_settings, init_resources=init_resources),
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
        postgres_check=lambda: check_postgres_connection(resolved_settings),
        redis_check=lambda: check_redis_connection(resolved_settings),
    )
    app.state.api_key_repository = ApiKeyRepository()
    app.state.rate_limiter = InMemoryRateLimiter(
        limit=resolved_settings.DEFAULT_RATE_LIMIT_PER_MINUTE,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app


def _build_lifespan(settings: Settings, *, init_resources: bool):
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if init_resources and settings.LANGFUSE_ENABLED:
                _flush_langfuse_client()

    return lifespan


def _flush_langfuse_client() -> None:
    try:
        from langfuse import get_client
    except ImportError:
        return
    client = get_client()
    if client is not None and hasattr(client, "flush"):
        client.flush()
