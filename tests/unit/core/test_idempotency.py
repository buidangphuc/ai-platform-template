from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import AppError
from app.core.idempotency import (
    get_idempotency_key,
    replay_or_start_idempotent_request,
    store_idempotent_response,
)
from app.modules.idempotency.store import IdempotencyCachedResponse


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


def _request(headers: dict[str, str], *, app: FastAPI | None = None):
    return SimpleNamespace(
        app=app or FastAPI(),
        headers=headers,
        method="POST",
        url=SimpleNamespace(path="/jobs"),
        state=SimpleNamespace(),
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
        get_idempotency_key(_request({"Idempotency-Key": "x" * 256}))

    assert exc_info.value.code == "invalid_idempotency_key"
    assert exc_info.value.status_code == 400


class _FakeIdempotencyStore:
    def __init__(
        self,
        cached: IdempotencyCachedResponse | None = None,
    ) -> None:
        self.cached = cached
        self.check_calls: list[dict[str, object]] = []
        self.store_calls: list[dict[str, object]] = []

    async def check_or_store(
        self,
        *,
        key: str,
        principal_id: str,
        request_hash: str,
        expires_at: datetime,
    ) -> IdempotencyCachedResponse | None:
        self.check_calls.append(
            {
                "key": key,
                "principal_id": principal_id,
                "request_hash": request_hash,
                "expires_at": expires_at,
            }
        )
        return self.cached

    async def store_response(
        self,
        *,
        key: str,
        principal_id: str,
        status_code: int,
        response_body: dict,
    ) -> None:
        self.store_calls.append(
            {
                "key": key,
                "principal_id": principal_id,
                "status_code": status_code,
                "response_body": response_body,
            }
        )

    async def close(self) -> None:
        return None


def _app_with_idempotency(store: _FakeIdempotencyStore) -> FastAPI:
    app = FastAPI()
    app.state.settings = _settings(IDEMPOTENCY_ENABLED=True)
    app.state.idempotency_store = store
    return app


async def test_idempotency_boundary_returns_none_when_no_key_is_present():
    store = _FakeIdempotencyStore()
    request = _request({}, app=_app_with_idempotency(store))

    response = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b"{}",
        expires_at=datetime(2026, 5, 22, tzinfo=UTC),
    )

    assert response is None
    assert store.check_calls == []


async def test_idempotency_boundary_replays_cached_response():
    store = _FakeIdempotencyStore(
        IdempotencyCachedResponse(status_code=202, body={"task_id": "t1"})
    )
    request = _request(
        {"Idempotency-Key": "job-1"},
        app=_app_with_idempotency(store),
    )

    response = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b'{"input":"hello"}',
        expires_at=datetime(2026, 5, 22, tzinfo=UTC),
    )

    assert response is not None
    assert response.status_code == 202
    assert response.body == b'{"task_id":"t1"}'
    assert request.state.idempotency_key == "job-1"


async def test_idempotency_boundary_stores_success_response_after_start():
    store = _FakeIdempotencyStore()
    expires_at = datetime(2026, 5, 22, tzinfo=UTC) + timedelta(hours=1)
    request = _request(
        {"Idempotency-Key": "job-1"},
        app=_app_with_idempotency(store),
    )

    response = await replay_or_start_idempotent_request(
        request,
        principal_id="user-1",
        body=b'{"input":"hello"}',
        expires_at=expires_at,
    )
    await store_idempotent_response(
        request,
        status_code=201,
        response_body={"id": "created"},
    )

    assert response is None
    assert store.check_calls[0]["key"] == "job-1"
    assert store.check_calls[0]["principal_id"] == "user-1"
    assert store.check_calls[0]["expires_at"] == expires_at
    assert store.store_calls == [
        {
            "key": "job-1",
            "principal_id": "user-1",
            "status_code": 201,
            "response_body": {"id": "created"},
        }
    ]


async def test_idempotency_boundary_fails_clearly_when_disabled():
    app = FastAPI()
    app.state.settings = _settings(IDEMPOTENCY_ENABLED=False)
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
