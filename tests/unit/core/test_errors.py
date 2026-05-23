from fastapi import APIRouter

from app.bootstrap.application import create_app
from app.core.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ServiceUnavailableError,
    TokenError,
    UnauthorizedError,
    UnprocessableEntityError,
    _http_error_code,
)
from tests.factories import api_client_for, build_test_settings


def test_typed_errors_carry_canonical_status_and_code():
    cases = [
        (BadRequestError(), 400, "bad_request"),
        (UnauthorizedError(), 401, "unauthorized"),
        (ForbiddenError(), 403, "forbidden"),
        (NotFoundError(), 404, "not_found"),
        (ConflictError(), 409, "conflict"),
        (UnprocessableEntityError(), 422, "unprocessable_entity"),
        (RateLimitError(), 429, "rate_limit_exceeded"),
        (ServerError(), 500, "internal_server_error"),
        (ServiceUnavailableError(), 503, "service_unavailable"),
        (TokenError(), 401, "invalid_token"),
    ]
    for exc, status, code in cases:
        assert exc.status_code == status, exc
        assert exc.code == code, exc
        assert isinstance(exc, AppError)


def test_http_status_code_map_covers_common_codes():
    assert _http_error_code(401) == "unauthorized"
    assert _http_error_code(409) == "conflict"
    assert _http_error_code(422) == "unprocessable_entity"
    assert _http_error_code(429) == "rate_limit_exceeded"
    assert _http_error_code(503) == "service_unavailable"
    assert _http_error_code(418) == "http_error"


async def test_typed_error_envelope_via_handler():
    router = APIRouter()

    @router.get("/conflict")
    async def conflict():
        raise ConflictError("Already exists", data={"field": "email"})

    app = create_app(settings=build_test_settings(), init_resources=False)
    app.include_router(router)

    async with api_client_for(app) as client:
        response = await client.get("/conflict", headers={"X-Request-ID": "req-c"})

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == "Already exists"
    assert body["error"]["data"] == {"field": "email"}
    assert body["error"]["request_id"] == "req-c"
