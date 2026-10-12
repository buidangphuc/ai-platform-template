from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.modules.platform.mongo.gateway import MongoGateway
from app.modules.platform.quota.models import (
    QuotaReservation,
    QuotaReservationStatus,
    QuotaUsage,
    QuotaUsageQuery,
    ReserveQuota,
)

DEFAULT_QUOTA_COUNTER_COLLECTION = "quota_counters"
DEFAULT_QUOTA_RESERVATION_COLLECTION = "quota_reservations"
# Documents are kept this long past ``reset_at`` before the TTL monitor drops
# them, so a late refund/finalize still finds its reservation and counter.
QUOTA_TTL_GRACE_SECONDS = 24 * 60 * 60


class MongoQuotaStore:
    def __init__(
        self,
        gateway: MongoGateway,
        *,
        counter_collection: str = DEFAULT_QUOTA_COUNTER_COLLECTION,
        reservation_collection: str = DEFAULT_QUOTA_RESERVATION_COLLECTION,
    ) -> None:
        self._counters = gateway.collection(counter_collection)
        self._reservations = gateway.collection(reservation_collection)

    async def ensure_indexes(self) -> None:
        """Create the indexes the store's atomicity relies on (idempotent).

        Call once at startup; ``create_index`` is a no-op when the index exists.
        """
        await self._counters.create_index(
            [
                ("subject_id", ASCENDING),
                ("resource", ASCENDING),
                ("window_key", ASCENDING),
            ],
            unique=True,
            name="uq_quota_counters_subject_resource_window",
        )
        await self._counters.create_index(
            [("reset_at", ASCENDING)],
            expireAfterSeconds=QUOTA_TTL_GRACE_SECONDS,
            name="ttl_quota_counters_reset_at",
        )
        await self._reservations.create_index(
            [
                ("subject_id", ASCENDING),
                ("resource", ASCENDING),
                ("window_key", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$type": "string"}},
            name="uq_quota_reservations_idempotency",
        )
        await self._reservations.create_index(
            [("reset_at", ASCENDING)],
            expireAfterSeconds=QUOTA_TTL_GRACE_SECONDS,
            name="ttl_quota_reservations_reset_at",
        )

    async def reserve(self, command: ReserveQuota) -> QuotaReservation | None:
        await self._migrate_active_counters(command)
        existing = await self._find_idempotent_reservation(command)
        if existing is not None:
            return await self._to_reservation(existing)

        counter_key = _counter_key(command)
        await self._counters.update_one(
            counter_key,
            {
                "$setOnInsert": {
                    **counter_key,
                    "used": 0,
                },
                "$set": {
                    "limit": command.limit,
                    "reset_at": command.reset_at,
                },
            },
            upsert=True,
        )
        counter = await self._counters.find_one_and_update(
            {
                **counter_key,
                "$expr": {
                    "$lte": [
                        {"$add": ["$used", command.cost]},
                        command.limit,
                    ]
                },
            },
            {
                "$inc": {"used": command.cost},
                "$set": {
                    "limit": command.limit,
                    "reset_at": command.reset_at,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if counter is None:
            return None

        reservation_doc = {
            "_id": command.reservation_id,
            "subject_id": command.subject_id,
            "resource": command.resource,
            "window_key": command.window_key,
            "cost": command.cost,
            "status": QuotaReservationStatus.RESERVED.value,
            "idempotency_key": command.idempotency_key,
            "reset_at": command.reset_at,
        }
        try:
            await self._reservations.insert_one(reservation_doc)
        except DuplicateKeyError:
            # A concurrent request with the same idempotency key won the race:
            # give back the capacity just taken and return its reservation.
            await self._counters.update_one(
                counter_key, {"$inc": {"used": -command.cost}}
            )
            existing = await self._find_idempotent_reservation(command)
            if existing is None:
                raise
            return await self._to_reservation(existing)
        return _reservation_from_doc(reservation_doc, _usage_from_counter(counter))

    async def finalize(self, reservation_id: str) -> QuotaUsage:
        claimed = await self._claim_reserved(
            reservation_id, QuotaReservationStatus.FINALIZED
        )
        if claimed is not None:
            return await self._usage_for_reservation(claimed)
        reservation = await self._require_reservation(reservation_id)
        if QuotaReservationStatus(reservation["status"]) == (
            QuotaReservationStatus.REFUNDED
        ):
            raise ValueError("refunded reservation cannot be finalized")
        return await self._usage_for_reservation(reservation)

    async def refund(self, reservation_id: str) -> QuotaUsage:
        claimed = await self._claim_reserved(
            reservation_id, QuotaReservationStatus.REFUNDED
        )
        if claimed is None:
            reservation = await self._require_reservation(reservation_id)
            if QuotaReservationStatus(reservation["status"]) == (
                QuotaReservationStatus.FINALIZED
            ):
                raise ValueError("finalized reservation cannot be refunded")
            return await self._usage_for_reservation(reservation)

        # Only the caller that flipped reserved -> refunded reaches this point,
        # so the counter is decremented exactly once.
        counter = await self._counters.find_one_and_update(
            {
                "subject_id": claimed["subject_id"],
                "resource": claimed["resource"],
                "window_key": claimed["window_key"],
            },
            {"$inc": {"used": -claimed["cost"]}},
            return_document=ReturnDocument.AFTER,
        )
        if counter is None:
            raise KeyError(reservation_id)
        return _usage_from_counter(counter)

    async def get_usage(self, query: QuotaUsageQuery) -> QuotaUsage:
        await self._migrate_active_counters(query)
        counter = await self._counters.find_one_and_update(
            {
                "subject_id": query.subject_id,
                "resource": query.resource,
                "window_key": query.window_key,
            },
            {
                "$set": {
                    "limit": query.limit,
                    "reset_at": query.reset_at,
                }
            },
            return_document=ReturnDocument.AFTER,
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
        return _usage_from_counter(counter)

    async def reset_usage(self, query: QuotaUsageQuery) -> QuotaUsage:
        key = {
            "subject_id": query.subject_id,
            "resource": query.resource,
        }
        await self._reservations.delete_many(key)
        await self._counters.delete_many(key)
        return _usage_from_query(query)

    async def reset_resource(self, resource: str) -> None:
        key = {"resource": resource}
        await self._reservations.delete_many(key)
        await self._counters.delete_many(key)

    async def close(self) -> None:
        return None

    async def _claim_reserved(
        self,
        reservation_id: str,
        new_status: QuotaReservationStatus,
    ) -> dict | None:
        """Atomically move ``reserved`` -> ``new_status``; None if not reserved."""
        return await self._reservations.find_one_and_update(
            {
                "_id": reservation_id,
                "status": QuotaReservationStatus.RESERVED.value,
            },
            {"$set": {"status": new_status.value}},
            return_document=ReturnDocument.BEFORE,
        )

    async def _find_idempotent_reservation(self, command: ReserveQuota) -> dict | None:
        if command.idempotency_key is None:
            return None
        return await self._reservations.find_one(
            {
                "subject_id": command.subject_id,
                "resource": command.resource,
                "window_key": command.window_key,
                "idempotency_key": command.idempotency_key,
            }
        )

    async def _migrate_active_counters(
        self,
        command: ReserveQuota | QuotaUsageQuery,
    ) -> None:
        now = datetime.now(UTC)
        cursor = self._counters.find(
            {
                "subject_id": command.subject_id,
                "resource": command.resource,
            }
        )
        target: dict | None = None
        stale: list[dict] = []
        async for counter in cursor:
            if counter["window_key"] == command.window_key:
                target = counter
            elif counter["reset_at"] > now:
                stale.append(counter)

        if not stale:
            if target is not None:
                await self._counters.update_one(
                    {
                        "subject_id": command.subject_id,
                        "resource": command.resource,
                        "window_key": command.window_key,
                    },
                    {
                        "$set": {
                            "limit": command.limit,
                            "reset_at": command.reset_at,
                        }
                    },
                )
            return

        counter_key = {
            "subject_id": command.subject_id,
            "resource": command.resource,
            "window_key": command.window_key,
        }
        for counter in stale:
            stale_key = {
                "subject_id": command.subject_id,
                "resource": command.resource,
                "window_key": counter["window_key"],
            }
            # Atomically claim the stale counter (delete returns its document)
            # so concurrent migrations never move the same usage twice.
            claimed = await self._counters.find_one_and_delete(stale_key)
            if claimed is None:
                continue
            await self._counters.update_one(
                counter_key,
                {
                    "$inc": {"used": int(claimed["used"])},
                    "$set": {
                        "limit": command.limit,
                        "reset_at": command.reset_at,
                    },
                },
                upsert=True,
            )
            await self._reservations.update_many(
                stale_key,
                {
                    "$set": {
                        "window_key": command.window_key,
                        "reset_at": command.reset_at,
                    }
                },
            )

    async def _require_reservation(self, reservation_id: str) -> dict:
        reservation = await self._reservations.find_one({"_id": reservation_id})
        if reservation is None:
            raise KeyError(reservation_id)
        return reservation

    async def _usage_for_reservation(self, reservation: dict) -> QuotaUsage:
        counter = await self._counters.find_one(
            {
                "subject_id": reservation["subject_id"],
                "resource": reservation["resource"],
                "window_key": reservation["window_key"],
            }
        )
        if counter is None:
            raise KeyError(reservation["_id"])
        return _usage_from_counter(counter)

    async def _to_reservation(self, reservation: dict) -> QuotaReservation:
        return _reservation_from_doc(
            reservation, await self._usage_for_reservation(reservation)
        )


def _counter_key(command: ReserveQuota) -> dict:
    return {
        "subject_id": command.subject_id,
        "resource": command.resource,
        "window_key": command.window_key,
    }


def _usage_from_counter(counter: dict) -> QuotaUsage:
    limit = int(counter["limit"])
    used = int(counter["used"])
    return QuotaUsage(
        subject_id=counter["subject_id"],
        resource=counter["resource"],
        window_key=counter["window_key"],
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        reset_at=counter["reset_at"],
    )


def _usage_from_query(query: QuotaUsageQuery) -> QuotaUsage:
    return QuotaUsage(
        subject_id=query.subject_id,
        resource=query.resource,
        window_key=query.window_key,
        used=0,
        limit=query.limit,
        remaining=query.limit,
        reset_at=query.reset_at,
    )


def _reservation_from_doc(doc: dict, usage: QuotaUsage) -> QuotaReservation:
    return QuotaReservation(
        id=doc["_id"],
        subject_id=doc["subject_id"],
        resource=doc["resource"],
        window_key=doc["window_key"],
        cost=doc["cost"],
        status=QuotaReservationStatus(doc["status"]),
        usage=usage,
        idempotency_key=doc.get("idempotency_key"),
    )
