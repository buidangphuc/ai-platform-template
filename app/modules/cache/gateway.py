from __future__ import annotations

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

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def close(self) -> None: ...
