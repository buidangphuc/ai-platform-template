from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from app.bootstrap.addons.quota import QuotaAddon
from app.bootstrap.resources import ApplicationResources
from app.core.mongo import build_mongo_client
from app.modules.platform.mongo.gateway import MongoGateway
from app.modules.platform.quota.adapters.mongo import MongoQuotaStore
from app.modules.platform.quota.factory import (
    build_mongo_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.models import (
    QuotaPolicy,
    QuotaReservationStatus,
    QuotaUsageQuery,
    ReserveQuota,
)
from app.modules.platform.quota.service import QuotaService
from tests.factories import build_test_settings, open_addon

RESET = datetime.now(UTC) + timedelta(minutes=5)
POLICY = QuotaPolicy(resource="tokens", limit=10, window_seconds=60)


@pytest.fixture()
async def store(mongo_gateway: MongoGateway) -> MongoQuotaStore:
    quota_store = build_mongo_quota_store(mongo_gateway)
    await quota_store.ensure_indexes()
    return quota_store


@pytest.fixture()
async def quota(store: MongoQuotaStore) -> AsyncIterator[QuotaService]:
    yield build_quota_service(store)


def _command(
    reservation_id: str, *, key: str | None = None, window: str = "w1"
) -> ReserveQuota:
    return ReserveQuota(
        subject_id="s",
        resource="r",
        window_key=window,
        limit=5,
        cost=1,
        reset_at=RESET,
        reservation_id=reservation_id,
        idempotency_key=key,
    )


async def _used(service: QuotaService) -> int:
    usage = await service.get_usage(subject_id="u1", resource="tokens", policy=POLICY)
    return usage.used


def test_build_mongo_client_is_tz_aware():
    client = build_mongo_client(build_test_settings())

    assert client.delegate.codec_options.tz_aware is True
    assert client.delegate.codec_options.tzinfo is UTC
    client.close()


async def test_refund_concurrent_decrements_counter_once(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    assert await store.reserve(_command("r1")) is not None

    results = await asyncio.gather(
        store.refund("r1"), store.refund("r1"), return_exceptions=True
    )

    assert all(not isinstance(r, Exception) for r in results)
    counter = await mongo_gateway.collection("quota_counters").find_one({})
    assert counter["used"] == 0


async def test_finalize_then_refund_is_rejected_and_keeps_usage(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    await store.reserve(_command("r1"))

    await store.finalize("r1")
    with pytest.raises(ValueError):
        await store.refund("r1")

    counter = await mongo_gateway.collection("quota_counters").find_one({})
    assert counter["used"] == 1


async def test_refund_missing_reservation_raises_key_error(store: MongoQuotaStore):
    with pytest.raises(KeyError):
        await store.refund("nope")


async def test_concurrent_refund_and_finalize_has_single_winner(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    await store.reserve(_command("r1"))

    results = await asyncio.gather(
        store.refund("r1"), store.finalize("r1"), return_exceptions=True
    )

    counter = await mongo_gateway.collection("quota_counters").find_one({})
    reservation = await mongo_gateway.collection("quota_reservations").find_one({})
    if reservation["status"] == QuotaReservationStatus.REFUNDED.value:
        assert counter["used"] == 0
        assert isinstance(results[1], ValueError)
    else:
        assert counter["used"] == 1
        assert isinstance(results[0], ValueError)


async def test_reserve_same_idempotency_key_returns_existing_without_leak(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    first, second = await asyncio.gather(
        store.reserve(_command("a", key="k")),
        store.reserve(_command("b", key="k")),
    )

    assert first is not None and second is not None
    assert first.id == second.id
    reservations = await mongo_gateway.collection("quota_reservations").count_documents(
        {}
    )
    counter = await mongo_gateway.collection("quota_counters").find_one({})
    assert reservations == 1
    assert counter["used"] == 1


async def test_migration_moves_usage_once_under_concurrency(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    await store.reserve(_command("r1", window="w1"))
    await store.reserve(_command("r2", window="w1"))

    query = QuotaUsageQuery(
        subject_id="s", resource="r", window_key="w2", limit=5, reset_at=RESET
    )
    await asyncio.gather(store.get_usage(query), store.get_usage(query))

    counters = await mongo_gateway.collection("quota_counters").find({}).to_list(None)
    reservations = (
        await mongo_gateway.collection("quota_reservations").find({}).to_list(None)
    )
    assert [d["window_key"] for d in counters] == ["w2"]
    assert counters[0]["used"] == 2
    assert {d["window_key"] for d in reservations} == {"w2"}


async def test_ensure_indexes_declares_unique_partial_and_ttl_indexes(
    store: MongoQuotaStore, mongo_gateway: MongoGateway
):
    await store.ensure_indexes()

    counters = await mongo_gateway.collection("quota_counters").index_information()
    reservations = await mongo_gateway.collection(
        "quota_reservations"
    ).index_information()
    counter_unique = [i for i in counters.values() if i.get("unique")]
    assert counter_unique[0]["key"] == [
        ("subject_id", 1),
        ("resource", 1),
        ("window_key", 1),
    ]
    reservation_unique = [i for i in reservations.values() if i.get("unique")]
    assert reservation_unique[0]["partialFilterExpression"] == {
        "idempotency_key": {"$type": "string"}
    }
    assert reservation_unique[0]["key"][-1] == ("idempotency_key", 1)
    assert any("expireAfterSeconds" in i for i in counters.values())
    assert any("expireAfterSeconds" in i for i in reservations.values())


async def test_quota_addon_ensures_mongo_indexes_when_opening(
    mongo_gateway: MongoGateway,
):
    resources = ApplicationResources(mongo=mongo_gateway)

    await open_addon(
        QuotaAddon(),
        resources,
        build_test_settings(
            QUOTA_ENABLED=True, QUOTA_BACKEND="mongo", MONGO_ENABLED=True
        ),
    )

    assert isinstance(resources.quota, QuotaService)
    counters = await mongo_gateway.collection("quota_counters").index_information()
    reservations = await mongo_gateway.collection(
        "quota_reservations"
    ).index_information()
    assert len(counters) > 1
    assert len(reservations) > 1


async def test_concurrent_same_idempotency_key_charges_once(quota: QuotaService):
    policy = QuotaPolicy(resource="tokens", limit=1_000, window_seconds=3600)

    for round_no in range(30):
        reservations = await asyncio.gather(
            *(
                quota.reserve(
                    subject_id="u1",
                    resource="tokens",
                    cost=3,
                    policy=policy,
                    idempotency_key=f"k{round_no}",
                )
                for _ in range(5)
            )
        )
        assert len({r.id for r in reservations}) == 1

    usage = await quota.get_usage(subject_id="u1", resource="tokens", policy=policy)
    assert usage.used == 30 * 3


async def test_idempotent_retry_storm_near_the_limit_is_not_rejected(
    quota: QuotaService,
):
    policy = QuotaPolicy(resource="tokens", limit=10, window_seconds=3600)

    reservations = await asyncio.gather(
        *(
            quota.reserve(
                subject_id="u1",
                resource="tokens",
                cost=3,
                policy=policy,
                idempotency_key="storm",
            )
            for _ in range(5)
        )
    )

    assert len({r.id for r in reservations}) == 1


async def test_concurrent_refunds_decrement_once(quota: QuotaService):
    reservation = await quota.reserve(
        subject_id="u1", resource="tokens", cost=4, policy=POLICY
    )

    await asyncio.gather(
        *(quota.refund(reservation.id) for _ in range(5)), return_exceptions=True
    )

    assert await _used(quota) == 0


async def test_window_rollover_reads_tz_aware_datetimes(
    quota: QuotaService, mongo_gateway: MongoGateway
):
    policy = QuotaPolicy(resource="tokens", limit=10, window_seconds=1)
    await quota.reserve(subject_id="u1", resource="tokens", cost=4, policy=policy)

    await asyncio.sleep(1.2)

    usage = await quota.get_usage(subject_id="u1", resource="tokens", policy=policy)
    assert usage.used == 0
    stored = await mongo_gateway.collection("quota_counters").find_one({})
    assert stored is not None
    assert stored["reset_at"].tzinfo is not None
