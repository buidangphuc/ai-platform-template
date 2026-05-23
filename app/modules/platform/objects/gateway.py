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

    async def list(
        self,
        prefix: str = "",
        *,
        limit: int = 100,
    ) -> list[str]:
        """List object keys under ``prefix`` (relative to the gateway prefix)."""
        ...

    async def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str: ...

    async def presign_put(
        self,
        key: str,
        *,
        expires_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        """Pre-signed URL the client can ``PUT`` to for direct upload."""
        ...

    async def close(self) -> None: ...
