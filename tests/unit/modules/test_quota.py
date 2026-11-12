from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.addons.quota import QuotaAddon
from app.bootstrap.resources import ApplicationResources
from app.core.errors import RateLimitError
from app.modules.platform.quota.factory import (
    build_postgres_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.models import (
    QuotaPolicy,
    QuotaReservationStatus,
)
from app.modules.platform.quota.service import QuotaService, resolve_fixed_window
from app.modules.platform.quota.store import QuotaStore
from tests.factories import build_test_settings, open_addon

RESOURCE = "legacy.description.generate"


@pytest.fixture()
def quota_store(pg_sessionmaker: async_sessionmaker[AsyncSession]) -> QuotaStore:
    return build_postgres_quota_store(pg_sessionmaker)


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _service(
    store: QuotaStore,
    *,
    limit: int = 2,
    window_seconds: int = 60,
    default_cost: int = 1,
) -> tuple[QuotaService, QuotaPolicy, MutableClock]:
    policy = QuotaPolicy(
        resource=RESOURCE,
        limit=limit,
        window_seconds=window_seconds,
        default_cost=default_cost,
    )
    clock = MutableClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = QuotaService(store=store, clock=clock)
    return service, policy, clock


async def test_quota_reserve_and_finalize_consumes_capacity(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=2)

    reservation = await service.reserve(subject_id="u1", policy=policy)
    usage = await service.finalize(reservation)

    assert reservation.status == QuotaReservationStatus.RESERVED
    assert reservation.usage.used == 1
    assert usage.used == 1
    assert usage.remaining == 1


async def test_quota_blocks_when_limit_is_exhausted(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=1)
    await service.reserve(subject_id="u1", policy=policy)

    with pytest.raises(RateLimitError) as exc_info:
        await service.reserve(subject_id="u1", policy=policy)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "60"}
    assert exc_info.value.data["resource"] == RESOURCE


async def test_quota_refund_restores_capacity_before_finalize(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=1)
    reservation = await service.reserve(subject_id="u1", policy=policy)

    usage = await service.refund(reservation)
    next_reservation = await service.reserve(subject_id="u1", policy=policy)

    assert usage.used == 0
    assert usage.remaining == 1
    assert next_reservation.usage.used == 1


async def test_quota_idempotency_key_does_not_double_charge(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=2)

    first = await service.reserve(
        subject_id="u1",
        policy=policy,
        idempotency_key="request-1",
    )
    second = await service.reserve(
        subject_id="u1",
        policy=policy,
        idempotency_key="request-1",
    )
    usage = await service.get_usage(subject_id="u1", policy=policy)

    assert second.id == first.id
    assert usage.used == 1
    assert usage.remaining == 1


async def test_quota_uses_new_capacity_after_window_rollover(quota_store: QuotaStore):
    service, policy, clock = _service(quota_store, limit=1, window_seconds=60)
    await service.reserve(subject_id="u1", policy=policy)

    clock.now += timedelta(seconds=60)
    usage = await service.get_usage(subject_id="u1", policy=policy)
    reservation = await service.reserve(subject_id="u1", policy=policy)

    assert usage.used == 0
    assert reservation.usage.used == 1


async def test_quota_reset_usage_clears_subject_resource_only(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=3)
    await service.reserve(subject_id="u1", policy=policy)
    await service.reserve(subject_id="u2", policy=policy)

    reset_usage = await service.reset_usage(subject_id="u1", policy=policy)
    u1 = await service.get_usage(subject_id="u1", policy=policy)
    u2 = await service.get_usage(subject_id="u2", policy=policy)

    assert reset_usage.used == 0
    assert u1.used == 0
    assert u2.used == 1


async def test_quota_reset_resource_clears_all_subjects(quota_store: QuotaStore):
    service, policy, _ = _service(quota_store, limit=3)
    await service.reserve(subject_id="u1", policy=policy)
    await service.reserve(subject_id="u2", policy=policy)

    await service.reset_resource(RESOURCE)
    u1 = await service.get_usage(subject_id="u1", policy=policy)
    u2 = await service.get_usage(subject_id="u2", policy=policy)

    assert u1.used == 0
    assert u2.used == 0


async def test_quota_reserves_against_the_policy_it_is_given(
    quota_store: QuotaStore,
):
    clock = MutableClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = QuotaService(store=quota_store, clock=clock)
    policy = QuotaPolicy(resource="custom.resource", limit=3, window_seconds=60)

    reservation = await service.reserve(subject_id="u1", policy=policy)

    assert reservation.usage.limit == 3
    assert reservation.usage.remaining == 2


def test_resolve_fixed_window_returns_epoch_bucket_and_reset_at():
    now = datetime.fromtimestamp(90, tz=UTC)
    window = resolve_fixed_window(now, 60)

    assert window.key == "1"
    assert window.reset_at == datetime.fromtimestamp(120, tz=UTC)


def test_build_quota_service_wraps_the_given_store(quota_store: QuotaStore):
    service = build_quota_service(quota_store)

    assert isinstance(service, QuotaService)


async def test_quota_addon_attaches_and_closes_service(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
):
    resources = ApplicationResources(sessionmaker=pg_sessionmaker)
    addon = QuotaAddon()

    stack = await open_addon(
        addon,
        resources,
        build_test_settings(QUOTA_ENABLED=True, DATABASE_ENABLED=True),
    )
    assert isinstance(resources.quota, QuotaService)

    await stack.aclose()
