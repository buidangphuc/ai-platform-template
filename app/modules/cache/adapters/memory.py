from __future__ import annotations

import time


class MemoryCacheGateway:
    def __init__(
        self, *, prefix: str = "app", default_ttl_seconds: float = 300
    ) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self.prefix = prefix
        self.default_ttl_seconds = default_ttl_seconds
        self._values: dict[str, tuple[bytes, float]] = {}
        self._closed = False

    async def get(self, key: str) -> bytes | None:
        self._ensure_open()
        cache_key = self._key(key)
        stored = self._values.get(cache_key)
        if stored is None:
            return None
        value, expires_at = stored
        if expires_at <= time.monotonic():
            self._values.pop(cache_key, None)
            return None
        return value

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        self._ensure_open()
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._values[self._key(key)] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        self._ensure_open()
        self._values.pop(self._key(key), None)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def close(self) -> None:
        self._closed = True
        self._values.clear()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("cache is closed")
