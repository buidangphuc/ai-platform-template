from __future__ import annotations

import time
from collections.abc import Mapping, Sequence


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
        return self._read(self._key(key))

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        self._ensure_open()
        ttl = self._resolve_ttl(ttl_seconds)
        self._values[self._key(key)] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> bool:
        self._ensure_open()
        return self._values.pop(self._key(key), None) is not None

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def get_many(self, keys: Sequence[str]) -> dict[str, bytes]:
        self._ensure_open()
        result: dict[str, bytes] = {}
        for key in keys:
            value = self._read(self._key(key))
            if value is not None:
                result[key] = value
        return result

    async def set_many(
        self,
        items: Mapping[str, bytes],
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        self._ensure_open()
        ttl = self._resolve_ttl(ttl_seconds)
        expires_at = time.monotonic() + ttl
        for key, value in items.items():
            self._values[self._key(key)] = (value, expires_at)

    async def delete_many(self, keys: Sequence[str]) -> int:
        self._ensure_open()
        removed = 0
        for key in keys:
            if self._values.pop(self._key(key), None) is not None:
                removed += 1
        return removed

    async def close(self) -> None:
        self._closed = True
        self._values.clear()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _resolve_ttl(self, ttl_seconds: float | None) -> float:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        return ttl

    def _read(self, cache_key: str) -> bytes | None:
        stored = self._values.get(cache_key)
        if stored is None:
            return None
        value, expires_at = stored
        if expires_at <= time.monotonic():
            self._values.pop(cache_key, None)
            return None
        return value

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("cache is closed")
