from fastapi import APIRouter, Response

from app.bootstrap.application import create_app
from app.core.errors import AppError
from app.core.request_context import get_request_id
from tests.factories import api_client_for, build_test_settings


async def test_app_error_uses_standard_envelope():
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AppError(code="test_error", message="Test error", status_code=418)

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
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

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
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

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
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

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
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

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
        response = await client.get(
            "/response-header", headers={"X-Request-ID": "req-middleware"}
        )

    request_id_headers = [
        value for name, value in response.headers.raw if name.lower() == b"x-request-id"
    ]
    assert request_id_headers == [b"req-middleware"]


async def test_404_uses_standard_error_envelope():
    app = create_app(settings=build_test_settings(), init_resources=False)

    async with api_client_for(app) as client:
        response = await client.get("/missing", headers={"X-Request-ID": "req-404"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "request_id": "req-404",
        }
    }


async def test_405_uses_standard_error_envelope():
    router = APIRouter()

    @router.get("/only-get")
    async def only_get():
        return {"ok": True}

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
        response = await client.post(
            "/only-get",
            headers={"X-Request-ID": "req-405"},
        )

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response.json()["error"]["request_id"] == "req-405"
