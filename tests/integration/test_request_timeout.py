import asyncio

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import build_test_settings


def _settings(*, timeout_seconds: int = 1) -> Settings:
    return build_test_settings(
        REQUEST_TIMEOUT_ENABLED=True,
        REQUEST_TIMEOUT_SECONDS=timeout_seconds,
    )


def _build_app(settings: Settings):
    app = create_app(settings=settings, init_resources=False)

    router = APIRouter()

    @router.get("/slow")
    async def slow():
        await asyncio.sleep(1.5)
        return {"ok": True}

    @router.get("/long/stream")
    async def long_stream():
        await asyncio.sleep(0.6)
        return {"streaming": True}

    app.include_router(router)
    return app


async def test_slow_request_times_out_with_504_envelope():
    app = _build_app(_settings(timeout_seconds=1))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/slow")

    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "request_timeout"


async def test_excluded_path_bypasses_timeout():
    app = _build_app(_settings(timeout_seconds=1))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        response = await client.get("/long/stream")

    assert response.status_code == 200
    assert response.json() == {"streaming": True}


async def test_timeout_disabled_lets_slow_request_finish():
    settings = _settings().model_copy(update={"REQUEST_TIMEOUT_ENABLED": False})
    app = _build_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        response = await client.get("/long/stream")

    assert response.status_code == 200
