from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime

from app.modules.platform.quota.models import (
    QuotaReservation,
    QuotaReservationStatus,
    QuotaUsage,
    QuotaUsageQuery,
    ReserveQuota,
)


@dataclass
class _Counter:
    subject_id: str
    resource: str
    window_key: str
    used: int
    limit: int
    reset_at: datetime


class MemoryQuotaStore:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, str, str], _Counter] = {}
        self._reservations: dict[str, QuotaReservation] = {}
        self._idempotency: dict[tuple[str, str, str, str], str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def reserve(self, command: ReserveQuota) -> QuotaReservation | None:
        self._ensure_open()
        async with self._lock:
            if command.idempotency_key is not None:
                idempotency_key = (
                    command.subject_id,
                    command.resource,
                    command.window_key,
                    command.idempotency_key,
                )
                existing_id = self._idempotency.get(idempotency_key)
                if existing_id is not None:
                    return self._reservations[existing_id]

            counter = self._counter_for(command)
            if counter.used + command.cost > command.limit:
                return None

            counter.used += command.cost
            counter.limit = command.limit
            counter.reset_at = command.reset_at
            reservation = QuotaReservation(
                id=command.reservation_id,
                subject_id=command.subject_id,
                resource=command.resource,
                window_key=command.window_key,
                cost=command.cost,
                status=QuotaReservationStatus.RESERVED,
                usage=_usage_from_counter(counter),
                idempotency_key=command.idempotency_key,
            )
            self._reservations[reservation.id] = reservation
            if command.idempotency_key is not None:
                self._idempotency[idempotency_key] = reservation.id
            return reservation

    async def finalize(self, reservation_id: str) -> QuotaUsage:
        self._ensure_open()
        async with self._lock:
            reservation = self._require_reservation(reservation_id)
            if reservation.status == QuotaReservationStatus.REFUNDED:
                raise ValueError("refunded reservation cannot be finalized")
            if reservation.status == QuotaReservationStatus.RESERVED:
                reservation = replace(
                    reservation,
                    status=QuotaReservationStatus.FINALIZED,
                    usage=self._usage_for_reservation(reservation),
                )
                self._reservations[reservation.id] = reservation
            return reservation.usage

    async def refund(self, reservation_id: str) -> QuotaUsage:
        self._ensure_open()
        async with self._lock:
            reservation = self._require_reservation(reservation_id)
            if reservation.status == QuotaReservationStatus.FINALIZED:
                raise ValueError("finalized reservation cannot be refunded")
            if reservation.status == QuotaReservationStatus.REFUNDED:
                return reservation.usage

            counter = self._counter_for_reservation(reservation)
            counter.used = max(counter.used - reservation.cost, 0)
            usage = _usage_from_counter(counter)
            self._reservations[reservation.id] = replace(
                reservation,
                status=QuotaReservationStatus.REFUNDED,
                usage=usage,
            )
            return usage

    async def get_usage(self, query: QuotaUsageQuery) -> QuotaUsage:
        self._ensure_open()
        async with self._lock:
            counter = self._counters.get(
                (query.subject_id, query.resource, query.window_key)
            )
            if counter is None:
                return QuotaUsage(
                    subject_id=query.subject_id,
                    resource=query.resource,
                    window_key=query.window_key,
                    used=0,
                    limit=query.limit,
                    remaining=query.limit,
                    reset_at=query.reset_at,
                )
            counter.limit = query.limit
            counter.reset_at = query.reset_at
            return _usage_from_counter(counter)

    async def close(self) -> None:
        self._closed = True
        self._counters.clear()
        self._reservations.clear()
        self._idempotency.clear()

    def _counter_for(self, command: ReserveQuota) -> _Counter:
        key = (command.subject_id, command.resource, command.window_key)
        counter = self._counters.get(key)
        if counter is None:
            counter = _Counter(
                subject_id=command.subject_id,
                resource=command.resource,
                window_key=command.window_key,
                used=0,
                limit=command.limit,
                reset_at=command.reset_at,
            )
            self._counters[key] = counter
        return counter

    def _counter_for_reservation(self, reservation: QuotaReservation) -> _Counter:
        key = (reservation.subject_id, reservation.resource, reservation.window_key)
        return self._counters[key]

    def _usage_for_reservation(self, reservation: QuotaReservation) -> QuotaUsage:
        return _usage_from_counter(self._counter_for_reservation(reservation))

    def _require_reservation(self, reservation_id: str) -> QuotaReservation:
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            raise KeyError(reservation_id)
        return reservation

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("quota store is closed")


def _usage_from_counter(counter: _Counter) -> QuotaUsage:
    limit = int(counter.limit)
    used = int(counter.used)
    return QuotaUsage(
        subject_id=counter.subject_id,
        resource=counter.resource,
        window_key=counter.window_key,
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        reset_at=counter.reset_at,
    )
