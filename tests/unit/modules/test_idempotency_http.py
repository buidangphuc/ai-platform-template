from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.errors import AppError
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.http import (
    IdempotentCall,
    get_idempotency_key,
    replay_or_start_idempotent_request,
    store_idempotent_response,
)
from app.modules.platform.idempotency.models import IdempotencyKey
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
