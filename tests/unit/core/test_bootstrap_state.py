import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import (
    attach_app_resource,
    clear_app_resource,
    get_app_settings,
    require_app_resource,
)
from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        AUTH_BEARER_TOKEN="test-token",  # pragma: allowlist secret
    )


def test_get_app_settings_reads_configured_settings() -> None:
    app = FastAPI()
    settings = _settings()
    app.state.settings = settings

    assert get_app_settings(app) is settings


def test_require_app_resource_raises_clear_service_error_when_missing() -> None:
    app = FastAPI()

    with pytest.raises(ServiceUnavailableError) as exc_info:
        require_app_resource(
            app,
            "cache",
            code="cache_not_configured",
            message="Cache gateway is disabled or lifespan has not opened it",
        )

    assert exc_info.value.code == "cache_not_configured"
    assert "disabled or lifespan" in exc_info.value.message


def test_attach_app_resource_tracks_state_key_for_shutdown_cleanup() -> None:
    app = FastAPI()
    resources = ApplicationResources()
    cache = object()

    attach_app_resource(app, resources, "cache", cache)

    assert app.state.cache is cache
    assert resources.state_keys == ["cache"]


def test_clear_app_resource_removes_existing_state_key() -> None:
    app = FastAPI()
    app.state.cache = object()

    clear_app_resource(app, "cache")

    assert not hasattr(app.state, "cache")
