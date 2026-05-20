from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.health import HealthService


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
    )
    app.include_router(build_api_router(resolved_settings))
    return app
