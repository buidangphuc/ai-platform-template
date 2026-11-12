from collections.abc import Callable

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.modules.platform.rate_limit.service import RateLimitResult
from tests.factories import build_test_settings


@pytest.fixture()
def make_settings(
    infra_settings: Callable[..., Settings], redis_client: Redis, redis_prefix: str
) -> Callable[..., Settings]:
    def build(**overrides: object) -> Settings:
        base: dict[str, object] = {
            "REDIS_ENABLED": True,
            "RATE_LIMIT_ENABLED": True,
            "RATE_LIMIT_REDIS_PREFIX": redis_prefix,
            "RATE_LIMIT_IP_ENABLED": True,
            "RATE_LIMIT_IP_PER_MINUTE": 2,
            "RATE_LIMIT_PRINCIPAL_ENABLED": False,
            "RATE_LIMIT_EXCLUDE_PATHS": "/healthz,/readyz",
        }
        base.update(overrides)
        return infra_settings(**base)

    return build


async def test_ip_rate_limit_blocks_requests_past_limit_and_emits_retry_after(
    make_settings: Callable[..., Settings],
):
    app = create_app(settings=make_settings(), init_resources=True)

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


async def test_ip_rate_limit_excludes_health_paths(
    make_settings: Callable[..., Settings],
):
    app = create_app(settings=make_settings(), init_resources=True)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            statuses = [(await client.get("/healthz")).status_code for _ in range(5)]

    assert all(status == 200 for status in statuses)


async def test_exclude_pattern_matches_whole_segments_only():
    class DenyAll:
        def __init__(self) -> None:
            self.keys: list[str] = []

        async def check(self, key: str) -> RateLimitResult:
            self.keys.append(key)
            return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=5)

    settings = build_test_settings(
        REDIS_ENABLED=True,
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_IP_ENABLED=True,
        RATE_LIMIT_EXCLUDE_PATHS="/stream",
    )
    app = create_app(settings=settings, init_resources=False)
    limiter = DenyAll()
    app.state.resources.ip_rate_limiter = limiter

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        excluded = await client.get("/api/v1/completions/stream")
        included = await client.get("/api/v1/streamers/1")

    assert excluded.status_code != 429
    assert included.status_code == 429
    assert len(limiter.keys) == 1


async def test_ip_rate_limit_passes_through_when_disabled(
    make_settings: Callable[..., Settings],
):
    settings = make_settings(RATE_LIMIT_IP_ENABLED=False, RATE_LIMIT_IP_PER_MINUTE=1)
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
