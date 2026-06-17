import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import build_test_settings


@pytest.fixture()
def test_settings() -> Settings:
    return build_test_settings(
        AUTH_SUBJECT="test-user",
        AUTH_ROLES="admin,developer",
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
    return {"Authorization": "Bearer test-token"}
