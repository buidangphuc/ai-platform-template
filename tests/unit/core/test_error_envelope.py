from fastapi import APIRouter

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.errors import AppError


def _settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )


async def test_app_error_uses_standard_envelope():
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AppError(code="test_error", message="Test error", status_code=418)

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/boom", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 418
    assert response.json() == {
        "error": {
            "code": "test_error",
            "message": "Test error",
            "request_id": "req-test",
        }
    }
