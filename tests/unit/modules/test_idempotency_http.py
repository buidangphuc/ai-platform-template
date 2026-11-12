import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.errors import AppError, register_exception_handlers
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.http import (
    IdempotentCall,
    get_idempotency_key,
    idempotent,
    replay_or_start_idempotent_request,
    store_idempotent_response,
)
from app.modules.platform.idempotency.models import IdempotencyKey
from app.modules.platform.identity.auth import require_principal
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def _request(headers: dict[str, str], *, app: FastAPI | None = None) -> Request:
    if app is None:
        app = FastAPI()
        app.state.settings = _settings()
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/jobs",
            "query_string": b"",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in headers.items()
            ],
            "app": app,
            "state": {},
        }
    )


def test_idempotency_key_is_optional():
    request = _request({})

    assert get_idempotency_key(request) is None
    assert request.state.idempotency_key is None


def test_idempotency_key_is_trimmed_and_stored_on_request_state():
    request = _request({"Idempotency-Key": " job-123 "})

    assert get_idempotency_key(request) == "job-123"
    assert request.state.idempotency_key == "job-123"


def test_idempotency_key_rejects_blank_header():
    with pytest.raises(AppError) as exc_info:
        get_idempotency_key(_request({"Idempotency-Key": "   "}))

    assert exc_info.value.code == "invalid_idempotency_key"
    assert exc_info.value.status_code == 400


def test_idempotency_key_rejects_oversized_header():
    with pytest.raises(AppError) as exc_info:
        get_idempotency_key(_request({"Idempotency-Key": "x" * 100}))

    assert exc_info.value.code == "invalid_idempotency_key"
    assert exc_info.value.status_code == 400


def test_idempotency_key_max_length_comes_from_settings():
    app = FastAPI()
    app.state.settings = _settings(IDEMPOTENCY_KEY_MAX_LENGTH=10)
    request = _request({"Idempotency-Key": "x" * 11}, app=app)

    with pytest.raises(AppError) as exc_info:
        get_idempotency_key(request)

    assert "max 10 characters" in exc_info.value.message


def _app_with_idempotency(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> FastAPI:
    app = FastAPI()
    app.state.settings = _settings(IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True)
    app.state.resources = ApplicationResources(
        idempotency_store=PostgresIdempotencyStore(
            sessionmaker, in_progress_timeout_seconds=600
        )
    )
    return app


def _expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


async def _rows(sessionmaker: async_sessionmaker[AsyncSession]) -> list[IdempotencyKey]:
    async with sessionmaker() as session:
        return list(await session.scalars(select(IdempotencyKey)))


async def test_idempotency_boundary_returns_none_when_no_key_is_present(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
):
    request = _request({}, app=_app_with_idempotency(pg_sessionmaker))

    response = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b"{}",
        expires_at=_expires_at(),
    )

    assert response is None
    async with pg_sessionmaker() as session:
        assert await session.scalar(select(func.count(IdempotencyKey.id))) == 0


async def test_idempotency_boundary_replays_cached_response(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
):
    app = _app_with_idempotency(pg_sessionmaker)
    first = await replay_or_start_idempotent_request(
        _request({"Idempotency-Key": "job-1"}, app=app),
        principal_id="user-1",
        body=b'{"input":"hello"}',
        expires_at=_expires_at(),
    )
    assert isinstance(first, IdempotentCall)
    await store_idempotent_response(
        first, status_code=202, response_body={"task_id": "t1"}
    )
    request = _request({"Idempotency-Key": "job-1"}, app=app)

    response = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b'{"input":"hello"}',
        expires_at=_expires_at(),
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert response.body == b'{"task_id":"t1"}'
    assert request.state.idempotency_key == "job-1"


async def test_idempotency_boundary_stores_success_response_after_start(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
):
    expires_at = _expires_at()
    request = _request(
        {"Idempotency-Key": "job-1"},
        app=_app_with_idempotency(pg_sessionmaker),
    )

    call = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b'{"input":"hello"}',
        expires_at=expires_at,
    )
    assert isinstance(call, IdempotentCall)
    stored = await store_idempotent_response(
        call,
        status_code=201,
        response_body={"id": "created"},
    )
    stored_again = await store_idempotent_response(
        call,
        status_code=500,
        response_body={"id": "overwritten"},
    )

    assert stored is True
    assert stored_again is False
    [row] = await _rows(pg_sessionmaker)
    assert row.key == "job-1"
    assert row.principal_id == "user-1"
    assert row.claim_token == call.claim_token
    assert row.expires_at == expires_at
    assert row.status == "completed"
    assert row.response_status_code == 201
    assert row.response_body == {"id": "created"}


async def test_idempotency_boundary_reports_a_still_running_request(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
):
    app = _app_with_idempotency(pg_sessionmaker)
    await replay_or_start_idempotent_request(
        _request({"Idempotency-Key": "job-1"}, app=app),
        principal_id="user-1",
        body=b"{}",
        expires_at=_expires_at(),
    )

    with pytest.raises(AppError) as exc_info:
        await replay_or_start_idempotent_request(
            _request({"Idempotency-Key": "job-1"}, app=app),
            principal_id="user-1",
            body=b"{}",
            expires_at=_expires_at(),
        )

    assert exc_info.value.code == "idempotency_key_in_progress"


async def test_idempotency_boundary_fails_clearly_when_disabled():
    app = FastAPI()
    app.state.settings = _settings(IDEMPOTENCY_ENABLED=False)
    app.state.resources = ApplicationResources()
    request = _request({"Idempotency-Key": "job-1"}, app=app)

    with pytest.raises(AppError) as exc_info:
        await replay_or_start_idempotent_request(
            request,
            principal_id="user-1",
            body=b"{}",
            expires_at=datetime(2026, 5, 22, tzinfo=UTC),
        )

    assert exc_info.value.code == "idempotency_disabled"
    assert exc_info.value.status_code == 503


HEADERS = {"Authorization": "Bearer test-token", "Idempotency-Key": "k1"}


class Public(BaseModel):
    id: int
    name: str = "unnamed"


Install = Callable[[APIRouter], None]


@pytest.fixture
def served(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[Install], Any]:
    def build(install: Install) -> AsyncClient:
        router = APIRouter(dependencies=[Depends(require_principal)])
        install(router)
        app = _app_with_idempotency(pg_sessionmaker)
        register_exception_handlers(app)
        app.include_router(router)
        return AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        )

    return build


async def test_failed_handler_releases_the_key(served, pg_sessionmaker):
    calls: list[int] = []

    def install(router: APIRouter) -> None:
        @router.post("/jobs")
        @idempotent
        async def jobs(request: Request) -> dict[str, int]:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return {"run": len(calls)}

    async with served(install) as client:
        first = await client.post("/jobs", headers=HEADERS, json={"a": 1})
        assert first.status_code == 500
        assert await _rows(pg_sessionmaker) == []

        second = await client.post("/jobs", headers=HEADERS, json={"a": 1})

    assert second.status_code == 200
    assert second.json() == {"run": 2}
    assert calls == [1, 1]


async def test_cancelled_handler_releases_the_key(served, pg_sessionmaker):
    entered = asyncio.Event()
    calls: list[int] = []

    def install(router: APIRouter) -> None:
        @router.post("/jobs")
        @idempotent
        async def jobs(request: Request) -> dict[str, int]:
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                await asyncio.Event().wait()
            return {"run": len(calls)}

    async with served(install) as client:
        pending = asyncio.create_task(client.post("/jobs", headers=HEADERS))
        await asyncio.wait_for(entered.wait(), timeout=5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert await _rows(pg_sessionmaker) == []

        second = await client.post("/jobs", headers=HEADERS)

    assert second.status_code == 200
    assert second.json() == {"run": 2}


async def test_replay_uses_the_declared_status_code(served):
    calls: list[int] = []

    def install(router: APIRouter) -> None:
        @router.post("/jobs", status_code=201)
        @idempotent
        async def jobs(request: Request) -> dict[str, int]:
            calls.append(1)
            return {"run": len(calls)}

    async with served(install) as client:
        first = await client.post("/jobs", headers=HEADERS)
        second = await client.post("/jobs", headers=HEADERS)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() == {"run": 1}
    assert len(calls) == 1


async def test_replay_is_filtered_by_the_response_model(served, pg_sessionmaker):
    def install(router: APIRouter) -> None:
        @router.post("/jobs", response_model=Public)
        @idempotent
        async def jobs(request: Request) -> dict[str, Any]:
            return {"id": 7, "name": "seven", "hidden": "internal"}

    async with served(install) as client:
        first = await client.post("/jobs", headers=HEADERS)
        second = await client.post("/jobs", headers=HEADERS)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"id": 7, "name": "seven"}
    [row] = await _rows(pg_sessionmaker)
    assert "hidden" not in str(row.response_body)


async def test_replay_honours_the_response_model_options(served):
    def install(router: APIRouter) -> None:
        @router.post("/jobs", response_model=Public, response_model_exclude_unset=True)
        @idempotent
        async def jobs(request: Request) -> Public:
            return Public(id=3)

    async with served(install) as client:
        first = await client.post("/jobs", headers=HEADERS)
        second = await client.post("/jobs", headers=HEADERS)

    assert first.json() == second.json() == {"id": 3}


@pytest.mark.parametrize("body", [[1, "two", {"three": 3}], [], "text", 7, None])
async def test_list_body_is_stored_and_replayed(served, body):
    calls: list[int] = []

    def install(router: APIRouter) -> None:
        @router.post("/jobs")
        @idempotent
        async def jobs(request: Request) -> Any:
            calls.append(1)
            return body

    async with served(install) as client:
        first = await client.post("/jobs", headers=HEADERS)
        second = await client.post("/jobs", headers=HEADERS)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == body
    assert len(calls) == 1


async def test_query_string_is_part_of_the_request_hash(served):
    calls: list[str] = []

    def install(router: APIRouter) -> None:
        @router.post("/jobs")
        @idempotent
        async def jobs(request: Request) -> dict[str, str]:
            calls.append(request.url.query)
            return {"query": request.url.query}

    async with served(install) as client:
        first = await client.post("/jobs?mode=a", headers=HEADERS)
        same = await client.post("/jobs?mode=a", headers=HEADERS)
        other = await client.post("/jobs?mode=b", headers=HEADERS)

    assert first.json() == same.json() == {"query": "mode=a"}
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "idempotency_key_conflict"
    assert calls == ["mode=a"]
