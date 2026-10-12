"""MongoQuotaStore against a real MongoDB (concurrency the in-memory fake can't model).

Set ``QUOTA_TEST_MONGO_URI`` (``mongodb://...``) to run; skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from app.core.mongo import build_mongo_client
from app.modules.platform.mongo.gateway import MongoGateway
from app.modules.platform.quota.factory import (
    build_mongo_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.models import QuotaPolicy
from app.modules.platform.quota.service import QuotaService
from tests.factories import build_test_settings

MONGO_URI = os.environ.get("QUOTA_TEST_MONGO_URI")
DATABASE = "aipt_quota_test"
POLICY = QuotaPolicy(resource="tokens", limit=10, window_seconds=60)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest_asyncio.fixture
async def quota() -> AsyncIterator[tuple[QuotaService, _Clock, MongoGateway]]:
    if MONGO_URI is None:
        pytest.skip("QUOTA_TEST_MONGO_URI not set")
    settings = build_test_settings(MONGODB_URI=MONGO_URI, MONGODB_DATABASE=DATABASE)
    client = build_mongo_client(settings)
    await client.drop_database(DATABASE)
    gateway = MongoGateway(client, database=DATABASE)
    store = build_mongo_quota_store(gateway)
    await store.ensure_indexes()
    clock = _Clock()
    service = build_quota_service(store)
    service._clock = clock
    yield service, clock, gateway
    client.close()


async def _used(service: QuotaService) -> int:
    usage = await service.get_usage(subject_id="u1", resource="tokens", policy=POLICY)
    return usage.used


async def test_concurrent_same_idempotency_key_charges_once(quota) -> None:
    service, _, _ = quota
    policy = QuotaPolicy(resource="tokens", limit=1_000, window_seconds=3600)

    # The race is timing-dependent; many rounds make a lost race near-certain.
    for round_no in range(30):
        reservations = await asyncio.gather(
            *(
                service.reserve(
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

    usage = await service.get_usage(subject_id="u1", resource="tokens", policy=policy)
    assert usage.used == 30 * 3


async def test_idempotent_retry_storm_near_the_limit_is_not_rejected(quota) -> None:
    service, _, _ = quota
    policy = QuotaPolicy(resource="tokens", limit=10, window_seconds=3600)

    reservations = await asyncio.gather(
        *(
            service.reserve(
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


async def test_concurrent_refunds_decrement_once(quota) -> None:
    service, _, _ = quota
    reservation = await service.reserve(
        subject_id="u1", resource="tokens", cost=4, policy=POLICY
    )

    await asyncio.gather(
        *(service.refund(reservation.id) for _ in range(5)), return_exceptions=True
    )

    assert await _used(service) == 0


async def test_window_rollover_reads_tz_aware_datetimes(quota) -> None:
    # Wall clock on purpose: the store compares reset_at with its own clock.
    service, _, gateway = quota
    service._clock = lambda: datetime.now(UTC)
    policy = QuotaPolicy(resource="tokens", limit=10, window_seconds=1)
    await service.reserve(subject_id="u1", resource="tokens", cost=4, policy=policy)

    await asyncio.sleep(1.2)

    usage = await service.get_usage(subject_id="u1", resource="tokens", policy=policy)
    assert usage.used == 0
    stored = await gateway.collection("quota_counters").find_one({})
    assert stored is not None
    assert stored["reset_at"].tzinfo is not None
