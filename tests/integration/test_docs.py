from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings


def _settings(*, docs_enabled: bool) -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        AUTH_BEARER_TOKEN="test-token",  # pragma: allowlist secret
        DOCS_ENABLED=docs_enabled,
    )


async def _get(app, path: str):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path)


async def test_docs_endpoints_exposed_when_enabled():
    app = create_app(settings=_settings(docs_enabled=True), init_resources=False)

    assert (await _get(app, "/docs")).status_code == 200
    assert (await _get(app, "/redoc")).status_code == 200
    assert (await _get(app, "/openapi.json")).status_code == 200


async def test_docs_endpoints_hidden_when_disabled():
    app = create_app(settings=_settings(docs_enabled=False), init_resources=False)

    assert (await _get(app, "/docs")).status_code == 404
    assert (await _get(app, "/redoc")).status_code == 404
    assert (await _get(app, "/openapi.json")).status_code == 404
