import asyncio
import logging

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.modules.platform.rate_limit.service import RateLimitResult
from tests.factories import build_test_settings

_ORIGIN = "https://app.example.com"


class _CountingLimiter:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.calls = 0

    async def check(self, key: str) -> RateLimitResult:
        self.calls += 1
        return RateLimitResult(
            allowed=self.allowed,
            remaining=0,
            retry_after_seconds=None if self.allowed else 7,
        )


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "CORS_ALLOW_ORIGINS": _ORIGIN,
        "SECURITY_HEADERS_ENABLED": True,
    }
    base.update(overrides)
    return build_test_settings(**base)


def _access_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "app.access"]


async def test_timeout_is_access_logged_as_504(caplog):
    app = create_app(
        settings=_settings(REQUEST_TIMEOUT_ENABLED=True, REQUEST_TIMEOUT_SECONDS=1),
        init_resources=False,
    )
    router = APIRouter()

    @router.get("/slow")
    async def slow():
        await asyncio.sleep(1.5)
        return {"ok": True}

    app.include_router(router)

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/slow", headers={"Origin": _ORIGIN})

    assert response.status_code == 504
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"
    lines = _access_lines(caplog)
    assert len(lines) == 1
    assert "path=/slow status=504" in lines[0]


async def test_rate_limited_response_is_logged_and_has_cors_and_security_headers(
    caplog,
):
    app = create_app(
        settings=_settings(
            REDIS_ENABLED=True, RATE_LIMIT_ENABLED=True, RATE_LIMIT_IP_ENABLED=True
        ),
        init_resources=False,
    )
    app.state.resources.ip_rate_limiter = _CountingLimiter(allowed=False)

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/completions",
                headers={"Origin": _ORIGIN, "X-Request-ID": "req-limited"},
            )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"] == "req-limited"
    lines = _access_lines(caplog)
    assert len(lines) == 1
    assert "status=429" in lines[0]
    assert "request_id=req-limited" in lines[0]


async def test_preflight_does_not_consume_rate_limit_budget():
    app = create_app(
        settings=_settings(
            REDIS_ENABLED=True, RATE_LIMIT_ENABLED=True, RATE_LIMIT_IP_ENABLED=True
        ),
        init_resources=False,
    )
    limiter = _CountingLimiter(allowed=False)
    app.state.resources.ip_rate_limiter = limiter

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.options(
            "/api/v1/completions",
            headers={
                "Origin": _ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert limiter.calls == 0


async def test_body_limit_response_has_cors_headers(caplog):
    app = create_app(
        settings=_settings(MAX_REQUEST_BODY_BYTES=10),
        init_resources=False,
    )

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/completions",
                headers={
                    "Origin": _ORIGIN,
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/json",
                },
                content=b'{"payload":"too-large"}',
            )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "status=413" in _access_lines(caplog)[0]


async def test_untrusted_host_response_is_logged_and_has_cors_headers(caplog):
    app = create_app(
        settings=_settings(TRUSTED_HOSTS="api.example.com"),
        init_resources=False,
    )

    with caplog.at_level(logging.INFO, logger="app.access"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://evil.example.com"
        ) as client:
            response = await client.get("/health", headers={"Origin": _ORIGIN})

    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert "status=400" in _access_lines(caplog)[0]
