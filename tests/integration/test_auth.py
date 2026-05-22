from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings


async def test_authenticated_endpoint_accepts_bearer_token(client):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-user",
        "type": "service",
        "scopes": ["admin", "developer"],
    }


async def test_authenticated_endpoint_rejects_missing_bearer_token(client):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_authenticated_endpoint_rejects_invalid_bearer_token(client):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_authenticated_endpoint_reports_unconfigured_auth(test_settings):
    app = create_app(
        settings=test_settings.model_copy(update={"AUTH_BEARER_TOKEN": ""}),
        init_resources=False,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "auth_not_configured"


async def test_authenticated_endpoint_returns_429_when_rate_limited():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        AUTH_BEARER_TOKEN="test-token",  # pragma: allowlist secret
        AUTH_SUBJECT="rate-limited-user",
        AUTH_ROLES="admin",
        DEFAULT_RATE_LIMIT_PER_MINUTE=1,
    )
    app = create_app(settings=settings, init_resources=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            first = await test_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer test-token"},
            )
            second = await test_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer test-token"},
            )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limit_exceeded"
