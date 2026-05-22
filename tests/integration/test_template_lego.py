from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


async def test_app_boots_with_new_lego_features_disabled():
    app = create_app(settings=_settings(), init_resources=False)

    async with app.router.lifespan_context(app):
        assert not hasattr(app.state, "cache")
        assert not hasattr(app.state, "webhook_signer")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/healthz")

    assert response.status_code == 200


async def test_cache_attaches_to_app_state_when_enabled():
    settings = _settings(CACHE_ENABLED=True, CACHE_BACKEND="memory")
    app = create_app(settings=settings, init_resources=False)

    async with app.router.lifespan_context(app):
        assert app.state.cache is not None
        await app.state.cache.set("key", b"value")
        assert await app.state.cache.get("key") == b"value"
