import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from app.bootstrap.addons.rate_limit import RateLimitAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.middleware import IPRateLimitMiddleware
from app.modules.platform.rate_limit.factory import (
    build_memory_rate_limiter,
    build_redis_rate_limiter,
)
from app.modules.platform.rate_limit.service import (
    InMemoryRateLimiter,
    RedisRateLimiter,
)
from tests.factories import build_test_settings, open_addon

# ----------------------------------------------------- InMemoryRateLimiter


async def test_in_memory_rate_limiter_allows_until_limit():
    now = 0.0
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60, clock=lambda: now)

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")
    third = await limiter.check("api-key-1")

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.remaining == 0


async def test_in_memory_rate_limiter_returns_retry_after_when_blocked():
    now = 30.0  # halfway through window
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, clock=lambda: now)

    await limiter.check("k")
    blocked = await limiter.check("k")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 30  # remaining window time


async def test_in_memory_rate_limiter_does_not_increment_past_limit():
    """Regression: blocked spammers should not keep growing the counter."""
    now = 0.0
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60, clock=lambda: now)

    await limiter.check("k")
    await limiter.check("k")
    for _ in range(100):
        result = await limiter.check("k")
        assert result.allowed is False

    window_index = int(now // 60)
    assert limiter._counts[("k", window_index)] == 2


async def test_sliding_window_blocks_burst_at_window_boundary():
    """Fixed window lets a client send 2x limit by straddling the boundary;
    sliding window's previous-bucket weighting must catch that."""
    now = 30.0  # halfway through window 0
    clock = lambda: now  # noqa: E731
    limiter = InMemoryRateLimiter(limit=10, window_seconds=60, clock=clock)

    # Burn the full budget in window 0
    for _ in range(10):
        result = await limiter.check("k")
        assert result.allowed

    # Cross into window 1 — the freshly-elapsed previous window still
    # contributes 100% at index boundary, then linearly decays.
    now = 60.0
    blocked = await limiter.check("k")
    assert blocked.allowed is False, "previous window must keep contributing"


async def test_sliding_window_allows_new_traffic_once_previous_fades():
    now = 0.0
    clock = lambda: now  # noqa: E731
    limiter = InMemoryRateLimiter(limit=10, window_seconds=60, clock=clock)

    for _ in range(10):
        await limiter.check("k")

    # Skip well past the previous window — its weight is 0.
    now = 120.0
    allowed = await limiter.check("k")
    assert allowed.allowed is True


async def test_in_memory_rate_limiter_evicts_stale_window_buckets():
    now = 0.0
    clock = lambda: now  # noqa: E731
    limiter = InMemoryRateLimiter(
        limit=1,
        window_seconds=10,
        clock=clock,
        eviction_threshold=5,
    )

    for i in range(5):
        await limiter.check(f"k{i}")

    # Move to a window 100 seconds later — previous buckets are stale
    now = 100.0
    await limiter.check("k-new")

    surviving_window_indices = {idx for (_, idx) in limiter._counts}
    assert surviving_window_indices == {10}  # only the new window remains


def test_in_memory_rate_limiter_rejects_invalid_limit():
    with pytest.raises(ValueError):
        InMemoryRateLimiter(limit=0)


# ----------------------------------------------------- RedisRateLimiter


async def _stored_counts(redis: Redis, prefix: str) -> list[int]:
    keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
    return [int(await redis.get(key)) for key in keys]


async def test_redis_rate_limiter_allows_within_limit(
    redis_client: Redis, redis_prefix: str
):
    limiter = RedisRateLimiter(
        redis=redis_client, limit=2, window_seconds=60, prefix=redis_prefix
    )

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")

    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0


async def test_redis_rate_limiter_blocks_and_returns_retry_after(
    redis_client: Redis, redis_prefix: str
):
    limiter = RedisRateLimiter(
        redis=redis_client, limit=1, window_seconds=30, prefix=redis_prefix
    )

    await limiter.check("api-key-1")
    blocked = await limiter.check("api-key-1")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds is not None
    assert 1 <= blocked.retry_after_seconds <= 30


async def test_redis_rate_limiter_does_not_increment_past_limit(
    redis_client: Redis, redis_prefix: str
):
    limiter = RedisRateLimiter(
        redis=redis_client, limit=1, window_seconds=3600, prefix=redis_prefix
    )

    await limiter.check("api-key-1")
    for _ in range(10):
        await limiter.check("api-key-1")

    assert await _stored_counts(redis_client, redis_prefix) == [1]


async def test_redis_rate_limiter_pods_share_windows_via_server_clock(
    redis_client: Redis, redis_prefix: str
):
    pod_a = RedisRateLimiter(
        redis=redis_client, limit=2, window_seconds=3600, prefix=redis_prefix
    )
    pod_b = RedisRateLimiter(
        redis=redis_client, limit=2, window_seconds=3600, prefix=redis_prefix
    )

    assert (await pod_a.check("k")).allowed
    assert (await pod_b.check("k")).allowed
    assert not (await pod_a.check("k")).allowed
    assert not (await pod_b.check("k")).allowed


def test_redis_rate_limiter_script_reads_redis_server_time():
    script = RedisRateLimiter._CHECK_SCRIPT

    assert "redis.call('TIME')" in script
    assert "ARGV[3]" not in script


async def test_redis_rate_limiter_lua_script_runs_on_real_redis(
    redis_client: Redis, redis_prefix: str
):
    limiter = RedisRateLimiter(
        redis=redis_client, limit=2, window_seconds=3600, prefix=redis_prefix
    )

    results = [await limiter.check("k") for _ in range(3)]

    assert [r.allowed for r in results] == [True, True, False]
    assert results[0].remaining == 1
    assert results[2].retry_after_seconds is not None


# ----------------------------------------------------- factory + addon


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_build_memory_rate_limiter_uses_limit_and_window():
    limiter = build_memory_rate_limiter(limit=5, window_seconds=30)

    assert isinstance(limiter, InMemoryRateLimiter)
    assert limiter.limit == 5


def test_build_redis_rate_limiter_uses_prefix(redis_client: Redis):
    limiter = build_redis_rate_limiter(
        redis_client, limit=5, window_seconds=30, prefix="rate-limit:ip"
    )

    assert isinstance(limiter, RedisRateLimiter)
    assert limiter.prefix == "rate-limit:ip"


async def test_rate_limit_addon_attaches_both_limiters_when_enabled(
    redis_client: Redis, redis_prefix: str
):
    resources = ApplicationResources(redis=redis_client)
    addon = RateLimitAddon()

    await open_addon(
        addon,
        resources,
        _settings(
            RATE_LIMIT_ENABLED=True,
            REDIS_ENABLED=True,
            RATE_LIMIT_BACKEND="redis",
            RATE_LIMIT_REDIS_PREFIX=redis_prefix,
        ),
    )

    assert isinstance(resources.principal_rate_limiter, RedisRateLimiter)
    assert resources.principal_rate_limiter.prefix == f"{redis_prefix}:principal"
    assert isinstance(resources.ip_rate_limiter, RedisRateLimiter)
    assert resources.ip_rate_limiter.prefix == f"{redis_prefix}:ip"
    assert (await resources.ip_rate_limiter.check("k")).allowed


async def test_rate_limit_addon_skips_disabled_layers():
    resources = ApplicationResources()
    addon = RateLimitAddon()

    await open_addon(
        addon,
        resources,
        _settings(RATE_LIMIT_IP_ENABLED=False, RATE_LIMIT_PRINCIPAL_ENABLED=True),
    )

    assert resources.principal_rate_limiter is not None
    assert resources.ip_rate_limiter is None


async def test_rate_limit_addon_close_is_a_no_op():
    resources = ApplicationResources()
    addon = RateLimitAddon()
    stack = await open_addon(addon, resources, _settings())

    await stack.aclose()

    assert resources.principal_rate_limiter is not None


def test_rate_limit_addon_respects_enabled_flag():
    addon = RateLimitAddon()

    assert addon.is_enabled(_settings(RATE_LIMIT_ENABLED=True)) is True
    assert addon.is_enabled(_settings(RATE_LIMIT_ENABLED=False)) is False


async def test_ip_rate_limit_middleware_reads_limiter_from_app_resources():
    app = FastAPI()
    app.state.resources = ApplicationResources(
        ip_rate_limiter=InMemoryRateLimiter(limit=1, window_seconds=60)
    )
    called = 0

    async def downstream(scope, receive, send):
        nonlocal called
        called += 1

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    middleware = IPRateLimitMiddleware(downstream)
    scope = {
        "type": "http",
        "path": "/x",
        "headers": [],
        "client": ("1.2.3.4", 1),
        "app": app,
    }

    await middleware(scope, receive, send)
    await middleware(scope, receive, send)

    assert called == 1
    assert sent[0]["status"] == 429
