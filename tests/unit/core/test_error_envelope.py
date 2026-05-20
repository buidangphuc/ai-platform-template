from fastapi import APIRouter, Response

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.errors import AppError
from app.core.request_context import get_request_id


def _settings() -> Settings:
    return Settings(
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
    )


async def test_app_error_uses_standard_envelope():
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AppError(code="test_error", message="Test error", status_code=418)

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/boom", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 418
    assert response.json() == {
        "error": {
            "code": "test_error",
            "message": "Test error",
            "request_id": "req-test",
        }
    }


async def test_request_id_context_resets_after_request():
    router = APIRouter()

    @router.get("/request-id")
    async def request_id():
        return {"request_id": get_request_id()}

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/request-id", headers={"X-Request-ID": "req-reset"}
        )

    assert response.json() == {"request_id": "req-reset"}
    assert get_request_id() == "-"


async def test_app_error_generates_request_id_without_header():
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AppError(code="test_error", message="Test error", status_code=418)

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/boom")

    request_id = response.json()["error"]["request_id"]
    assert response.status_code == 418
    assert request_id.startswith("req_")
    assert response.headers["X-Request-ID"] == request_id


async def test_request_id_uses_first_incoming_header():
    router = APIRouter()

    @router.get("/request-id")
    async def request_id():
        return {"request_id": get_request_id()}

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/request-id",
            headers=[
                ("X-Request-ID", "req-first"),
                ("X-Request-ID", "req-second"),
            ],
        )

    assert response.json() == {"request_id": "req-first"}
    assert response.headers["X-Request-ID"] == "req-first"


async def test_request_id_replaces_existing_response_header():
    router = APIRouter()

    @router.get("/response-header")
    async def response_header(response: Response):
        response.headers["X-Request-ID"] = "req-downstream"
        return {"ok": True}

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/response-header", headers={"X-Request-ID": "req-middleware"}
        )

    request_id_headers = [
        value for name, value in response.headers.raw if name.lower() == b"x-request-id"
    ]
    assert request_id_headers == [b"req-middleware"]
