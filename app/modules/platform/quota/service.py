from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from math import ceil

from app.core.errors import RateLimitError
from app.modules.platform.quota.models import (
    QuotaPolicy,
    QuotaReservation,
    QuotaUsage,
    QuotaUsageQuery,
    QuotaWindow,
    ReserveQuota,
)
from app.modules.platform.quota.store import QuotaPolicyStore, QuotaStore


class QuotaService:
    def __init__(
        self,
        *,
        store: QuotaStore,
        policy_store: QuotaPolicyStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._policy_store = policy_store
        self._clock = clock

    async def reserve(
        self,
        *,
        subject_id: str,
        resource: str,
        cost: int | None = None,
        policy: QuotaPolicy | None = None,
        idempotency_key: str | None = None,
    ) -> QuotaReservation:
        resolved_policy = await self._resolve_policy(resource, policy)
        resolved_cost = resolved_policy.default_cost if cost is None else cost
        if resolved_cost <= 0:
            raise ValueError("cost must be positive")

        now = _ensure_utc(self._clock())
        window = resolve_fixed_window(now, resolved_policy.window_seconds)
        command = ReserveQuota.create(
            subject_id=subject_id,
            resource=resolved_policy.resource,
            window_key=window.key,
            limit=resolved_policy.limit,
            cost=resolved_cost,
            reset_at=window.reset_at,
            idempotency_key=idempotency_key,
        )
        reservation = await self._store.reserve(command)
        if reservation is None:
            raise RateLimitError(
                message=f"Quota exceeded for resource {resolved_policy.resource}",
                retry_after_seconds=_retry_after_seconds(window.reset_at, now),
                data={
                    "subject_id": subject_id,
                    "resource": resolved_policy.resource,
                    "limit": resolved_policy.limit,
                    "cost": resolved_cost,
                    "reset_at": window.reset_at.isoformat(),
                },
            )
        return reservation

    async def finalize(self, reservation: QuotaReservation | str) -> QuotaUsage:
        reservation_id = _reservation_id(reservation)
        return await self._store.finalize(reservation_id)

    async def refund(self, reservation: QuotaReservation | str) -> QuotaUsage:
        reservation_id = _reservation_id(reservation)
        return await self._store.refund(reservation_id)

    async def get_usage(
        self,
        *,
        subject_id: str,
        resource: str,
        policy: QuotaPolicy | None = None,
    ) -> QuotaUsage:
        resolved_policy = await self._resolve_policy(resource, policy)
        now = _ensure_utc(self._clock())
        window = resolve_fixed_window(now, resolved_policy.window_seconds)
        return await self._store.get_usage(
            QuotaUsageQuery(
                subject_id=subject_id,
                resource=resolved_policy.resource,
                window_key=window.key,
                limit=resolved_policy.limit,
                reset_at=window.reset_at,
            )
        )

    async def close(self) -> None:
        await self._store.close()

    async def _resolve_policy(
        self,
        resource: str,
        policy: QuotaPolicy | None,
    ) -> QuotaPolicy:
        if policy is not None:
            if policy.resource != resource:
                raise ValueError("policy resource must match requested resource")
            return policy
        stored = await self._policy_store.get_policy(resource)
        if stored is None:
            raise KeyError(f"No quota policy configured for resource {resource!r}")
        return stored


def resolve_fixed_window(now: datetime, window_seconds: int) -> QuotaWindow:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    current = _ensure_utc(now)
    epoch_seconds = int(current.timestamp())
    window_index = epoch_seconds // window_seconds
    reset_epoch = (window_index + 1) * window_seconds
    reset_at = datetime.fromtimestamp(reset_epoch, tz=UTC)
    return QuotaWindow(key=str(window_index), reset_at=reset_at)


def _reservation_id(reservation: QuotaReservation | str) -> str:
    if isinstance(reservation, QuotaReservation):
        return reservation.id
    return reservation


def _retry_after_seconds(reset_at: datetime, now: datetime) -> int:
    return max(ceil((reset_at - now).total_seconds()), 1)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
