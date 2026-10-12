import pytest
from httpx import AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import api_client_for, build_test_settings


@pytest.fixture()
def test_settings() -> Settings:
    return build_test_settings()


@pytest.fixture()
async def client(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)
    async with api_client_for(app) as test_client:
        yield test_client


@pytest.fixture()
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}
