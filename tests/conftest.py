import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings


@pytest.fixture()
def test_settings() -> Settings:
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
        API_KEY_BOOTSTRAP_TOKEN="test-bootstrap-token",  # pragma: allowlist secret
    )


@pytest.fixture()
async def client(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.fixture()
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
        json={"name": "test-client"},
    )
    api_key = response.json()["api_key"]
    return {"Authorization": f"Bearer {api_key}"}
