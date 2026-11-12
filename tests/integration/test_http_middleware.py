import logging
import re
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.bootstrap.features.completions import completions_feature
from app.core.config import Settings
from app.core.middleware import RequestBodyLimitMiddleware, RequestBodyTooLarge
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from tests.factories import api_client_for, build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


class _CompletionHandler:
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="ok", model="test")

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk]:
        yield CompletionStreamChunk(delta="ok")


async def test_cors_preflight_uses_configured_origins():
    app = create_app(
        settings=_settings(CORS_ALLOW_ORIGINS="https://app.example.com"),
        init_resources=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/api/v1/completions",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://app.example.com"
    )


async def test_trusted_hosts_rejects_untrusted_host():
    app = create_app(
        settings=_settings(TRUSTED_HOSTS="api.example.com"),
        init_resources=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://evil.example.com",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 400


async def test_request_body_limit_returns_standard_envelope():
    app = create_app(
        settings=_settings(MAX_REQUEST_BODY_BYTES=10),
        init_resources=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/completions",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
                "X-Request-ID": "req-body",
            },
            content=b'{"payload":"too-large"}',
        )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "request_body_too_large",
        "message": "Request body too large",
        "request_id": "req-body",
    }


async def test_access_log_records_request_context(caplog):
    app = create_app(
        features=(
            completions_feature(
                handler_factory=lambda resources, settings: _CompletionHandler()
            ),
        ),
        settings=_settings(),
        init_resources=False,
    )

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with api_client_for(app) as client:
            response = await client.post(
                "/api/v1/completions",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Request-ID": "req-log",
                },
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert any("method=POST" in message for message in messages)
    assert any("path=/api/v1/completions" in message for message in messages)
    assert any("status=200" in message for message in messages)
    assert any("request_id=req-log" in message for message in messages)
    assert any("principal=test-user" in message for message in messages)


async def test_security_headers_are_disabled_by_default():
    app = create_app(settings=_settings(), init_resources=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/healthz")

    assert "x-content-type-options" not in response.headers
    assert "strict-transport-security" not in response.headers


async def test_security_headers_can_enable_hsts():
    app = create_app(
        settings=_settings(
            SECURITY_HEADERS_ENABLED=True,
            SECURITY_HSTS_ENABLED=True,
            SECURITY_HSTS_MAX_AGE_SECONDS=123,
        ),
        init_resources=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/healthz")

    assert response.headers["strict-transport-security"] == (
        "max-age=123; includeSubDomains"
    )


_GENERATED_ID = re.compile(r"req_[0-9a-f]{32}")


@pytest.mark.parametrize(
    "value",
    ["a b", "id=1", "xé", "a;b", "<script>"],
)
async def test_invalid_request_id_is_replaced(value: str, caplog):
    app = create_app(settings=_settings(), init_resources=False)

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with api_client_for(app) as client:
            response = await client.get(
                "/healthz", headers={"X-Request-ID": value.encode("utf-8")}
            )

    echoed = response.headers["x-request-id"]
    assert _GENERATED_ID.fullmatch(echoed)
    messages = [record.getMessage() for record in caplog.records]
    assert any(f"request_id={echoed}" in message for message in messages)
    assert not any(value in message for message in messages)


async def test_valid_request_id_is_kept():
    app = create_app(settings=_settings(), init_resources=False)

    async with api_client_for(app) as client:
        for value in ("abc-123", "A.b_c-9", "x" * 128):
            response = await client.get("/healthz", headers={"X-Request-ID": value})
            assert response.headers["x-request-id"] == value


async def test_overlong_request_id_is_replaced():
    app = create_app(settings=_settings(), init_resources=False)

    async with api_client_for(app) as client:
        response = await client.get("/healthz", headers={"X-Request-ID": "x" * 129})

    assert _GENERATED_ID.fullmatch(response.headers["x-request-id"])


async def test_body_limit_fallback_reader_validates_the_request_id():
    seen: list[dict] = []

    async def inner(scope, receive, send):
        raise AssertionError("body must not reach the application")

    async def send(message):
        seen.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = RequestBodyLimitMiddleware(inner, max_body_bytes=1)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [
            (b"x-request-id", b"bad id=1"),
            (b"content-length", b"50"),
        ],
    }

    await middleware(scope, receive, send)

    assert seen[0]["status"] == 413
    request_id = dict(seen[0]["headers"])[b"x-request-id"].decode()
    assert _GENERATED_ID.fullmatch(request_id)


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def test_chunked_body_over_limit_gets_413():
    app = create_app(
        settings=_settings(MAX_REQUEST_BODY_BYTES=10),
        init_resources=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/completions",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
                "X-Request-ID": "req-chunked",
            },
            content=_chunks(b'{"payload":', b'"too-large"}'),
        )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "request_body_too_large",
        "message": "Request body too large",
        "request_id": "req-chunked",
    }


async def test_chunked_413_replaces_the_response_of_an_app_that_swallows_the_error():
    sent: list[dict] = []

    async def reading_app(scope, receive, send):
        try:
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break
        except Exception:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad"})

    async def send(message):
        sent.append(message)

    chunks = iter(
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    middleware = RequestBodyLimitMiddleware(reading_app, max_body_bytes=10)
    await middleware(
        {"type": "http", "method": "POST", "path": "/x", "headers": []},
        receive,
        send,
    )

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert [m["status"] for m in starts] == [413]
    assert b"request_body_too_large" in b"".join(m.get("body", b"") for m in sent)
    assert b"bad" not in b"".join(m.get("body", b"") for m in sent)


async def test_response_already_started_is_not_replaced_by_413():
    sent: list[dict] = []

    async def streaming_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await receive()
        await receive()
        await send({"type": "http.response.body", "body": b"done"})

    async def send(message):
        sent.append(message)

    chunks = iter(
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": True},
        ]
    )

    async def receive():
        return next(chunks)

    middleware = RequestBodyLimitMiddleware(streaming_app, max_body_bytes=10)
    with pytest.raises(RequestBodyTooLarge):
        await middleware(
            {"type": "http", "method": "POST", "path": "/x", "headers": []},
            receive,
            send,
        )

    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [200]
