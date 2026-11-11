from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.bootstrap.resources import ApplicationResources
from app.core.errors import register_exception_handlers
from app.modules.platform.idempotency.http import idempotent
from app.modules.platform.idempotency.store import (
    IdempotencyCachedResponse,
    IdempotencyClaim,
)
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.quota.adapters.memory import MemoryQuotaStore
from app.modules.platform.quota.factory import build_quota_service
from app.modules.platform.quota.http import require_quota
from app.modules.platform.quota.models import QuotaPolicy
from tests.factories import build_test_settings

HEADERS = {"Authorization": "Bearer test-token"}


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}

    async def check_or_store(
        self, *, key: str, principal_id: str, request_hash: str, expires_at: datetime
    ) -> IdempotencyCachedResponse | IdempotencyClaim:
        record = self.records.get((principal_id, key))
        if record is not None and record["response"] is not None:
            status_code, body = record["response"]
            return IdempotencyCachedResponse(status_code=status_code, body=body)
        token = str(uuid4())
        self.records[(principal_id, key)] = {"token": token, "response": None}
        return IdempotencyClaim(token=token)

    async def store_response(
        self,
        *,
        key: str,
        principal_id: str,
        claim_token: str,
        status_code: int,
        response_body: Any,
    ) -> bool:
        self.records[(principal_id, key)]["response"] = (
            status_code,
            dict(response_body),
        )
        return True

    async def delete_expired(self, *, before: datetime, limit: int) -> int:
        return 0

    async def close(self) -> None:
        return None


@pytest.fixture
async def guarded() -> AsyncIterator[tuple[AsyncClient, list[str]]]:
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
            MemoryQuotaStore(),
            policies={"limited": QuotaPolicy("limited", limit=1, window_seconds=3600)},
        ),
        idempotency_store=MemoryIdempotencyStore(),
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
