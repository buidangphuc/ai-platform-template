from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings

_LARGE_PAYLOAD = "x" * 4096
_SMALL_PAYLOAD = "x" * 16


def _settings(*, gzip_enabled: bool, min_size: int = 1024) -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        AUTH_BEARER_TOKEN="test-token",  # pragma: allowlist secret
        GZIP_ENABLED=gzip_enabled,
        GZIP_MIN_SIZE=min_size,
    )


def _build_app(settings: Settings):
    app = create_app(settings=settings, init_resources=False)

    router = APIRouter()

    @router.get("/large")
    async def large():
        return {"payload": _LARGE_PAYLOAD}

    @router.get("/small")
    async def small():
        return {"payload": _SMALL_PAYLOAD}

    app.include_router(router)
    return app


async def test_gzip_compresses_large_response_when_enabled():
    app = _build_app(_settings(gzip_enabled=True))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/large", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


async def test_gzip_skips_small_response_below_minimum_size():
    app = _build_app(_settings(gzip_enabled=True))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/small", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") != "gzip"


async def test_gzip_does_not_compress_when_disabled():
    app = _build_app(_settings(gzip_enabled=False))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/large", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") != "gzip"


async def test_gzip_respects_client_without_accept_encoding():
    app = _build_app(_settings(gzip_enabled=True))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/large", headers={"Accept-Encoding": "identity"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") != "gzip"
