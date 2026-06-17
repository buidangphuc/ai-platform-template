from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_BACKEND": "memory",
        "RATE_LIMIT_IP_ENABLED": True,
        "RATE_LIMIT_IP_PER_MINUTE": 2,
        "RATE_LIMIT_PRINCIPAL_ENABLED": False,
        "RATE_LIMIT_EXCLUDE_PATHS": "/healthz,/readyz",
    }
    base.update(overrides)
    return build_test_settings(**base)


async def test_ip_rate_limit_blocks_requests_past_limit_and_emits_retry_after():
    app = create_app(settings=_settings(), init_resources=True)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.get("/api/v1/completions")  # 401 but counts
            second = await client.get("/api/v1/completions")
            third = await client.get("/api/v1/completions")

    assert first.status_code in {401, 405}
    assert second.status_code in {401, 405}
    assert third.status_code == 429
    assert third.headers.get("retry-after") is not None
    assert third.json()["error"]["code"] == "rate_limit_exceeded"


async def test_ip_rate_limit_excludes_health_paths():
    app = create_app(settings=_settings(), init_resources=True)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            statuses = [(await client.get("/healthz")).status_code for _ in range(5)]

    assert all(status == 200 for status in statuses)


async def test_ip_rate_limit_passes_through_when_disabled():
    settings = _settings(RATE_LIMIT_IP_ENABLED=False, RATE_LIMIT_IP_PER_MINUTE=1)
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            statuses = [
                (await client.get("/api/v1/completions")).status_code for _ in range(5)
            ]

    assert 429 not in statuses
