import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from app.modules.cache.gateway import CacheGateway

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

    async def test_delete_removes_key(self, cache: CacheGateway):
        await cache.set("delete-me", b"value")
        await cache.delete("delete-me")

        assert await cache.get("delete-me") is None

    async def test_ttl_expiry_removes_key(self, cache: CacheGateway):
        await cache.set("short", b"value", ttl_seconds=0.01)
        await asyncio.sleep(0.03)

        assert await cache.get("short") is None
        assert await cache.exists("short") is False
