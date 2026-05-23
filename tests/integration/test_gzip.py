from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import build_test_settings

_LARGE_PAYLOAD = "x" * 4096


def _settings(*, gzip_enabled: bool, min_size: int = 1024) -> Settings:
    return build_test_settings(
        GZIP_ENABLED=gzip_enabled,
        GZIP_MIN_SIZE=min_size,
    )


def _build_app(settings: Settings):
    app = create_app(settings=settings, init_resources=False)

    router = APIRouter()

    @router.get("/large")
    async def large():
        return {"payload": _LARGE_PAYLOAD}

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


async def test_gzip_does_not_compress_when_disabled():
    app = _build_app(_settings(gzip_enabled=False))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/large", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") != "gzip"
