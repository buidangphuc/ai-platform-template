from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.resources import ApplicationResources
from app.core.errors import register_exception_handlers
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.http import idempotent
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.quota.factory import (
    build_postgres_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.http import require_quota
from app.modules.platform.quota.models import QuotaPolicy
from tests.factories import build_test_settings

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
async def guarded(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[AsyncClient, list[str]]]:
    calls: list[str] = []
    router = APIRouter(dependencies=[Depends(require_principal)])

    @router.post("/limited", dependencies=[Depends(require_quota("limited"))])
    async def limited() -> dict[str, str]:
        calls.append("limited")
        return {"ok": "yes"}

    @router.post("/jobs")
    @idempotent
    async def jobs(request: Request) -> dict[str, Any]:
        calls.append("jobs")
        return {"run": len(calls)}

    app = FastAPI()
    app.state.settings = build_test_settings(
        IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True
    )
    app.state.resources = ApplicationResources(
        quota=build_quota_service(
            build_postgres_quota_store(pg_sessionmaker),
            policies={"limited": QuotaPolicy("limited", limit=1, window_seconds=3600)},
        ),
        idempotency_store=PostgresIdempotencyStore(
            pg_sessionmaker, in_progress_timeout_seconds=60
        ),
    )
    register_exception_handlers(app)
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, calls


async def test_quota_exceeded_is_429_and_handler_does_not_run(guarded) -> None:
    client, calls = guarded

    first = await client.post("/limited", headers=HEADERS)
    second = await client.post("/limited", headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
    assert calls == ["limited"]


async def test_idempotent_replay_runs_handler_once(guarded) -> None:
    client, calls = guarded
    headers = {**HEADERS, "Idempotency-Key": "k1"}

    first = await client.post("/jobs", headers=headers, json={"a": 1})
    second = await client.post("/jobs", headers=headers, json={"a": 1})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"run": 1}
    assert calls == ["jobs"]


async def test_without_key_handler_runs_every_time(guarded) -> None:
    client, calls = guarded

    first = await client.post("/jobs", headers=HEADERS)
    second = await client.post("/jobs", headers=HEADERS)

    assert first.json() == {"run": 1}
    assert second.json() == {"run": 2}
    assert calls == ["jobs", "jobs"]
