from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings

BOOTSTRAP_HEADERS = {"X-Bootstrap-Token": "test-bootstrap-token"}


async def test_create_api_key_returns_secret_once(client):
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=BOOTSTRAP_HEADERS,
        json={"name": "local-test"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "local-test"
    assert body["api_key"].startswith("ak_")
    assert body["api_key_id"]


async def test_create_api_key_requires_bootstrap_token(client):
    response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_authenticated_endpoint_accepts_api_key(client):
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=BOOTSTRAP_HEADERS,
        json={"name": "local-test"},
    )
    api_key = created.json()["api_key"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["auth_type"] == "api_key"


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
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
        API_KEY_BOOTSTRAP_TOKEN="test-bootstrap-token",  # pragma: allowlist secret
        DEFAULT_RATE_LIMIT_PER_MINUTE=1,
    )
    app = create_app(settings=settings, init_resources=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        created = await test_client.post(
            "/api/v1/auth/api-keys",
            headers=BOOTSTRAP_HEADERS,
            json={"name": "local-test"},
        )
        api_key = created.json()["api_key"]

        first = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        second = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limit_exceeded"
