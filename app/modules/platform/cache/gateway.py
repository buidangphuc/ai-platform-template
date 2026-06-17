from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class CacheGateway(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: float | None = None,
    ) -> None: ...

    async def delete(self, key: str) -> bool:
        """Delete ``key``. Returns ``True`` if the key existed before deletion."""
        ...

    async def exists(self, key: str) -> bool: ...

    async def get_many(self, keys: Sequence[str]) -> dict[str, bytes]:
        """Return only keys that were present (missing keys omitted)."""
        ...

    async def set_many(
        self,
        items: Mapping[str, bytes],
        *,
        ttl_seconds: float | None = None,
    ) -> None: ...

    async def delete_many(self, keys: Sequence[str]) -> int:
        """Delete keys in bulk. Returns the number of keys actually removed."""
        ...

    async def close(self) -> None: ...
