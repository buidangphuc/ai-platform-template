from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisCacheGateway:
    def __init__(
        self,
        *,
        redis: Redis,
        prefix: str = "app",
        default_ttl_seconds: float = 300,
    ) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self.redis = redis
        self.prefix = prefix
        self.default_ttl_seconds = default_ttl_seconds

    async def get(self, key: str) -> bytes | None:
        value = await self.redis.get(self._key(key))
        return (
            value if value is None or isinstance(value, bytes) else str(value).encode()
        )

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        await self.redis.set(self._key(key), value, px=max(math.ceil(ttl * 1000), 1))

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        return bool(await self.redis.exists(self._key(key)))

    async def close(self) -> None:
        return None

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"
