"""Catch-all handler: unhandled errors still use the envelope and request id."""

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from tests.factories import build_test_settings


async def test_unhandled_exception_returns_envelope_with_request_id():
    router = APIRouter()

    @router.get("/explode")
    async def explode():
        raise RuntimeError("secret internal detail")

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/explode", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "req-500"
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "Internal server error",
            "request_id": "req-500",
        }
    }
    assert "secret internal detail" not in response.text
