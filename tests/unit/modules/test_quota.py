from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.errors import RateLimitError
from app.modules.platform.quota.adapters.memory import MemoryQuotaStore
from app.modules.platform.quota.factory import QuotaAddon, build_quota_service
from app.modules.platform.quota.models import (
    QuotaPolicy,
    QuotaReservationStatus,
)
from app.modules.platform.quota.service import QuotaService, resolve_fixed_window
from app.modules.platform.quota.store import StaticQuotaPolicyStore
from tests.factories import build_test_settings

RESOURCE = "legacy.description.generate"


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _service(
    *,
    limit: int = 2,
    window_seconds: int = 60,
    default_cost: int = 1,
) -> tuple[QuotaService, MutableClock]:
    policy = QuotaPolicy(
        resource=RESOURCE,
        limit=limit,
        window_seconds=window_seconds,
        default_cost=default_cost,
    )
    clock = MutableClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = QuotaService(
        store=MemoryQuotaStore(),
        policy_store=StaticQuotaPolicyStore({RESOURCE: policy}),
        clock=clock,
    )
    return service, clock


async def test_quota_reserve_and_finalize_consumes_capacity():
    service, _ = _service(limit=2)

    reservation = await service.reserve(subject_id="u1", resource=RESOURCE)
    usage = await service.finalize(reservation)

    assert reservation.status == QuotaReservationStatus.RESERVED
    assert reservation.usage.used == 1
    assert usage.used == 1
    assert usage.remaining == 1


async def test_quota_blocks_when_limit_is_exhausted():
    service, _ = _service(limit=1)
    await service.reserve(subject_id="u1", resource=RESOURCE)

    with pytest.raises(RateLimitError) as exc_info:
        await service.reserve(subject_id="u1", resource=RESOURCE)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "60"}
    assert exc_info.value.data["resource"] == RESOURCE


async def test_quota_refund_restores_capacity_before_finalize():
    service, _ = _service(limit=1)
    reservation = await service.reserve(subject_id="u1", resource=RESOURCE)

    usage = await service.refund(reservation)
    next_reservation = await service.reserve(subject_id="u1", resource=RESOURCE)

    assert usage.used == 0
    assert usage.remaining == 1
    assert next_reservation.usage.used == 1


async def test_quota_idempotency_key_does_not_double_charge():
    service, _ = _service(limit=2)

    first = await service.reserve(
        subject_id="u1",
        resource=RESOURCE,
        idempotency_key="request-1",
    )
    second = await service.reserve(
        subject_id="u1",
        resource=RESOURCE,
        idempotency_key="request-1",
    )
    usage = await service.get_usage(subject_id="u1", resource=RESOURCE)

    assert second.id == first.id
    assert usage.used == 1
    assert usage.remaining == 1


async def test_quota_uses_new_capacity_after_window_rollover():
    service, clock = _service(limit=1, window_seconds=60)
    await service.reserve(subject_id="u1", resource=RESOURCE)

    clock.now += timedelta(seconds=60)
    usage = await service.get_usage(subject_id="u1", resource=RESOURCE)
    reservation = await service.reserve(subject_id="u1", resource=RESOURCE)

    assert usage.used == 0
    assert reservation.usage.used == 1


async def test_quota_accepts_explicit_policy_without_policy_store_entry():
    clock = MutableClock(datetime(2026, 1, 1, tzinfo=UTC))
    service = QuotaService(
        store=MemoryQuotaStore(),
        policy_store=StaticQuotaPolicyStore(),
        clock=clock,
    )
    policy = QuotaPolicy(resource="custom.resource", limit=3, window_seconds=60)

    reservation = await service.reserve(
        subject_id="u1",
        resource="custom.resource",
        policy=policy,
    )

    assert reservation.usage.limit == 3
    assert reservation.usage.remaining == 2


def test_resolve_fixed_window_returns_epoch_bucket_and_reset_at():
    now = datetime.fromtimestamp(90, tz=UTC)
    window = resolve_fixed_window(now, 60)

    assert window.key == "1"
    assert window.reset_at == datetime.fromtimestamp(120, tz=UTC)


def test_build_quota_service_defaults_to_memory_backend():
    service = build_quota_service(build_test_settings())

    assert isinstance(service, QuotaService)


def test_build_quota_service_requires_sessionmaker_for_postgres():
    with pytest.raises(RuntimeError, match="sessionmaker"):
        build_quota_service(build_test_settings(QUOTA_BACKEND="postgres"))


async def test_quota_addon_attaches_and_closes_service():
    app = FastAPI()
    resources = ApplicationResources()
    addon = QuotaAddon()

    await addon.open(app, resources, build_test_settings(QUOTA_ENABLED=True))
    assert isinstance(resources.quota, QuotaService)

    await addon.close(app, resources)
    assert resources.quota is None
