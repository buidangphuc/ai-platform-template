from __future__ import annotations

from typing import Protocol

from app.modules.platform.quota.models import (
    QuotaPolicy,
    QuotaReservation,
    QuotaUsage,
    QuotaUsageQuery,
    ReserveQuota,
)


class QuotaStore(Protocol):
    async def reserve(self, command: ReserveQuota) -> QuotaReservation | None:
        """Atomically reserve quota or return ``None`` when the limit is exhausted."""
        ...

    async def finalize(self, reservation_id: str) -> QuotaUsage: ...

    async def refund(self, reservation_id: str) -> QuotaUsage: ...

    async def get_usage(self, query: QuotaUsageQuery) -> QuotaUsage: ...

    async def reset_usage(self, query: QuotaUsageQuery) -> QuotaUsage: ...

    async def reset_resource(self, resource: str) -> None: ...

    async def close(self) -> None: ...


class QuotaPolicyStore(Protocol):
    async def get_policy(self, resource: str) -> QuotaPolicy | None: ...


class StaticQuotaPolicyStore:
    def __init__(self, policies: dict[str, QuotaPolicy] | None = None) -> None:
        self._policies = dict(policies or {})

    async def get_policy(self, resource: str) -> QuotaPolicy | None:
        return self._policies.get(resource)
