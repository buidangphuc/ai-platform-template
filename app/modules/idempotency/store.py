from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class IdempotencyCachedResponse:
    status_code: int
    body: dict[str, Any]


@runtime_checkable
class IdempotencyStore(Protocol):
    async def check_or_store(
        self,
        *,
        key: str,
        principal_id: str,
        request_hash: str,
        expires_at: datetime,
    ) -> IdempotencyCachedResponse | None: ...

    async def store_response(
        self,
        *,
        key: str,
        principal_id: str,
        status_code: int,
        response_body: Mapping[str, Any],
    ) -> None: ...

    async def close(self) -> None: ...
