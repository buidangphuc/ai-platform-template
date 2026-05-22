from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectGateway(Protocol):
    async def put(
        self,
        key: str,
        value: bytes,
        *,
        content_type: str | None = None,
    ) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str: ...

    async def close(self) -> None: ...
