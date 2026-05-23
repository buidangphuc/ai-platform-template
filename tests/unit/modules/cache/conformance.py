import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from app.modules.platform.cache.gateway import CacheGateway

GatewayFactory = Callable[[], Awaitable[CacheGateway]]


class CacheGatewayConformance:
    @pytest.fixture
    async def cache(
        self,
        cache_factory: GatewayFactory,
    ) -> AsyncIterator[CacheGateway]:
        instance = await cache_factory()
        try:
            yield instance
        finally:
            await instance.close()

    async def test_set_then_get_round_trip(self, cache: CacheGateway):
        await cache.set("answer", b"42")

        assert await cache.get("answer") == b"42"
        assert await cache.exists("answer") is True

    async def test_get_missing_returns_none(self, cache: CacheGateway):
        assert await cache.get("missing") is None
        assert await cache.exists("missing") is False

    async def test_delete_returns_true_when_key_existed(self, cache: CacheGateway):
        await cache.set("delete-me", b"value")

        assert await cache.delete("delete-me") is True
        assert await cache.get("delete-me") is None

    async def test_delete_returns_false_when_key_missing(self, cache: CacheGateway):
        assert await cache.delete("never-existed") is False

    async def test_ttl_expiry_removes_key(self, cache: CacheGateway):
        await cache.set("short", b"value", ttl_seconds=0.01)
        await asyncio.sleep(0.03)

        assert await cache.get("short") is None
        assert await cache.exists("short") is False

    async def test_get_many_returns_only_present_keys(self, cache: CacheGateway):
        await cache.set("a", b"1")
        await cache.set("c", b"3")

        result = await cache.get_many(["a", "b", "c"])

        assert result == {"a": b"1", "c": b"3"}

    async def test_get_many_with_empty_keys_returns_empty(self, cache: CacheGateway):
        assert await cache.get_many([]) == {}

    async def test_set_many_writes_each_pair(self, cache: CacheGateway):
        await cache.set_many({"x": b"1", "y": b"2"}, ttl_seconds=30)

        assert await cache.get("x") == b"1"
        assert await cache.get("y") == b"2"

    async def test_delete_many_returns_count_of_actually_removed_keys(
        self, cache: CacheGateway
    ):
        await cache.set("a", b"1")
        await cache.set("c", b"3")

        removed = await cache.delete_many(["a", "b", "c"])

        assert removed == 2
        assert await cache.get("a") is None
        assert await cache.get("c") is None

    async def test_delete_many_with_empty_keys_returns_zero(self, cache: CacheGateway):
        assert await cache.delete_many([]) == 0
