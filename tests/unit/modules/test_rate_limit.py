import pytest
from fastapi import FastAPI

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


class FakeRedis:
    """Python stub mirroring the Lua script, including its server-side clock.

    ``server_time`` plays Redis ``TIME``: the limiter passes no timestamp, so
    the window is whatever the *server* says, shared by every client.
    """

    def __init__(self, server_time: float = 0.0) -> None:
        self.server_time = server_time
        self.values: dict[str, int] = {}
        self.eval_calls: list[tuple] = []

    async def eval(
        self,
        script: str,
        num_keys: int,
        base_key: str,
        window_seconds: int,
        limit: int,
    ) -> list[int]:
        self.eval_calls.append((script, num_keys, base_key, window_seconds, limit))
        now = self.server_time
        window_index = int(now // window_seconds)
        elapsed = now - window_index * window_seconds
        current_key = f"{base_key}:{window_index}"
        previous_key = f"{base_key}:{window_index - 1}"
        current = self.values.get(current_key, 0)
        previous = self.values.get(previous_key, 0)
        previous_weight = max(1.0 - elapsed / window_seconds, 0.0)
        weighted = current + int(previous * previous_weight)
        retry_after = max(int(window_seconds - elapsed), 1)

        if weighted >= limit:
            return [weighted, retry_after, 0]

        self.values[current_key] = current + 1
        weighted_after = (current + 1) + int(previous * previous_weight)
        return [weighted_after, retry_after, 1]


async def test_redis_rate_limiter_allows_within_limit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")

    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0


async def test_redis_rate_limiter_blocks_and_returns_retry_after():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=1, window_seconds=30)

    await limiter.check("api-key-1")
    blocked = await limiter.check("api-key-1")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 30


async def test_redis_rate_limiter_does_not_increment_past_limit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=1, window_seconds=30)

    await limiter.check("api-key-1")
    for _ in range(10):
        await limiter.check("api-key-1")

    # Lua script returns without INCR once limit is reached
    current_key_value = next(iter(redis.values.values()))
    assert current_key_value == 1


async def test_redis_rate_limiter_pods_share_windows_via_server_clock():
    """Two pods (two limiter instances) hitting one Redis count into the same
    window: nothing about the window is derived from process-local time."""
    redis = FakeRedis(server_time=45.0)
    pod_a = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)
    pod_b = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    assert (await pod_a.check("k")).allowed
    assert (await pod_b.check("k")).allowed
    assert not (await pod_a.check("k")).allowed
    assert not (await pod_b.check("k")).allowed


def test_redis_rate_limiter_script_reads_redis_server_time():
    script = RedisRateLimiter._CHECK_SCRIPT

    assert "redis.call('TIME')" in script
    assert "ARGV[3]" not in script  # no client-supplied timestamp/elapsed


async def test_redis_rate_limiter_lua_script_against_fakeredis():
    """Runs the real Lua (TIME included) when fakeredis has the lupa extra."""
    pytest.importorskip("lupa")
    from fakeredis import FakeAsyncRedis

    redis = FakeAsyncRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

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


def test_build_redis_rate_limiter_uses_prefix():
    limiter = build_redis_rate_limiter(
        FakeRedis(), limit=5, window_seconds=30, prefix="rate-limit:ip"
    )

    assert isinstance(limiter, RedisRateLimiter)
    assert limiter.prefix == "rate-limit:ip"


async def test_rate_limit_addon_attaches_both_limiters_when_enabled():
    FastAPI()
    resources = ApplicationResources(redis=FakeRedis())
    addon = RateLimitAddon()

    await open_addon(
        addon,
        resources,
        _settings(
            RATE_LIMIT_ENABLED=True,
            REDIS_ENABLED=True,
            RATE_LIMIT_BACKEND="redis",
        ),
    )

    assert isinstance(resources.principal_rate_limiter, RedisRateLimiter)
    assert resources.principal_rate_limiter.prefix == "rate-limit:principal"
    assert isinstance(resources.ip_rate_limiter, RedisRateLimiter)
    assert resources.ip_rate_limiter.prefix == "rate-limit:ip"


async def test_rate_limit_addon_skips_disabled_layers():
    FastAPI()
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
