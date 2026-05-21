import logging

from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.middleware import RequestBodyLimitMiddleware


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "REDIS_PASSWORD": "",  # pragma: allowlist secret
        "REDIS_DATABASE": 0,
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


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
            "/api/v1/auth/me",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
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


async def test_request_body_limit_rejects_streamed_body_without_content_length():
    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "http.request" and not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(downstream, max_body_bytes=3)
    incoming = [
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cd", "more_body": False},
    ]
    sent = []
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [(b"x-request-id", b"req-stream")],
    }

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)

    assert sent[0]["status"] == 413
    assert sent[1]["body"] == (
        b'{"error": {"code": "request_body_too_large", '
        b'"message": "Request body too large", "request_id": "req-stream"}}'
    )


async def test_access_log_records_request_context(caplog):
    app = create_app(settings=_settings(), init_resources=False)

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Request-ID": "req-log",
                },
            )

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert any("method=GET" in message for message in messages)
    assert any("path=/api/v1/auth/me" in message for message in messages)
    assert any("status=200" in message for message in messages)
    assert any("request_id=req-log" in message for message in messages)
    assert any("principal=local-user" in message for message in messages)
