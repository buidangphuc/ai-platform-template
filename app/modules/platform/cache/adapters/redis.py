from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
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
        return _coerce_bytes(await self.redis.get(self._key(key)))

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        ttl_ms = self._resolve_ttl_ms(ttl_seconds)
        await self.redis.set(self._key(key), value, px=ttl_ms)

    async def delete(self, key: str) -> bool:
        return bool(await self.redis.delete(self._key(key)))

    async def exists(self, key: str) -> bool:
        return bool(await self.redis.exists(self._key(key)))

    async def get_many(self, keys: Sequence[str]) -> dict[str, bytes]:
        if not keys:
            return {}
        cache_keys = [self._key(k) for k in keys]
        raw_values = await self.redis.mget(cache_keys)
        result: dict[str, bytes] = {}
        for original_key, raw in zip(keys, raw_values, strict=True):
            value = _coerce_bytes(raw)
            if value is not None:
                result[original_key] = value
        return result

    async def set_many(
        self,
        items: Mapping[str, bytes],
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        if not items:
            return
        ttl_ms = self._resolve_ttl_ms(ttl_seconds)
        pipeline = self.redis.pipeline()
        for key, value in items.items():
            pipeline.set(self._key(key), value, px=ttl_ms)
        await pipeline.execute()

    async def delete_many(self, keys: Sequence[str]) -> int:
        if not keys:
            return 0
        cache_keys = [self._key(k) for k in keys]
        return int(await self.redis.delete(*cache_keys))

    async def close(self) -> None:
        return None

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _resolve_ttl_ms(self, ttl_seconds: float | None) -> int:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        return max(math.ceil(ttl * 1000), 1)


def _coerce_bytes(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return str(value).encode()
