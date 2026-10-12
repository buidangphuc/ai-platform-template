from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class IdempotencyCachedResponse:
    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """Proof of a claim; only its holder may complete the key."""

    token: str


class IdempotencyStore(Protocol):
    async def check_or_store(
        self,
        *,
        key: str,
        principal_id: str,
        request_hash: str,
        expires_at: datetime,
    ) -> IdempotencyCachedResponse | IdempotencyClaim:
        """Claim the key (fresh or reclaimed) or replay its completed response."""
        ...

    async def store_response(
        self,
        *,
        key: str,
        principal_id: str,
        claim_token: str,
        status_code: int,
        response_body: Mapping[str, Any],
    ) -> bool:
        """Complete the claim; ``False`` when it was fenced off (reclaimed/completed)."""
        ...

    async def delete_expired(self, *, before: datetime, limit: int) -> int:
        """Delete at most ``limit`` records expired before ``before``."""
        ...

    async def close(self) -> None: ...
