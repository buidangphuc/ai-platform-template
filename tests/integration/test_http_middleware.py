import logging
from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from tests.factories import build_test_settings


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
        completion_handler=_CompletionHandler(),
        settings=_settings(),
        init_resources=False,
    )

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
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
    assert any("principal=local-user" in message for message in messages)


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
