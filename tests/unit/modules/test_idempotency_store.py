from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.idempotency.adapters import PostgresIdempotencyStore
from app.modules.idempotency.factory import IdempotencyAddon, build_idempotency_store
from app.modules.idempotency.models import IdempotencyKey
from app.modules.idempotency.service import (
    IdempotencyCachedResponse,
    build_request_hash,
    check_or_store_idempotency_key,
    store_idempotency_response,
)
from app.modules.idempotency.store import IdempotencyStore


class _FakeSession:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added = []
        self.flushed = False

    async def scalar(self, statement):
        return self.existing

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True


def test_request_hash_scopes_key_to_method_path_body_and_principal():
    first = build_request_hash(
        method="post",
        path="/api/v1/completions",
        body=b'{"message":"hello"}',
        principal_id="user-a",
    )
    same = build_request_hash(
        method="POST",
        path="/api/v1/completions",
        body=b'{"message":"hello"}',
        principal_id="user-a",
    )
    other_user = build_request_hash(
        method="POST",
        path="/api/v1/completions",
        body=b'{"message":"hello"}',
        principal_id="user-b",
    )

    assert first == same
    assert first != other_user


async def test_check_or_store_creates_in_progress_record_for_new_key():
    session = _FakeSession()
    request_hash = build_request_hash(
        method="POST",
        path="/jobs",
        body=b"{}",
        principal_id="svc-local",
    )
    expires_at = datetime(2026, 5, 22, tzinfo=UTC)

    cached = await check_or_store_idempotency_key(
        session,
        key="job-1",
        principal_id="svc-local",
        request_hash=request_hash,
        expires_at=expires_at,
    )

    assert cached is None
    assert session.flushed is True
    assert len(session.added) == 1
    record = session.added[0]
    assert record.key == "job-1"
    assert record.principal_id == "svc-local"
    assert record.request_hash == request_hash
    assert record.status == "in_progress"
    assert record.expires_at == expires_at


async def test_check_or_store_returns_cached_response_for_completed_record():
    request_hash = build_request_hash(
        method="POST",
        path="/jobs",
        body=b"{}",
        principal_id="svc-local",
    )
    record = IdempotencyKey(
        key="job-1",
        principal_id="svc-local",
        request_hash=request_hash,
        status="completed",
        response_status_code=202,
        response_body={"job_id": "j1"},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = _FakeSession(existing=record)

    cached = await check_or_store_idempotency_key(
        session,
        key="job-1",
        principal_id="svc-local",
        request_hash=request_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    assert cached == IdempotencyCachedResponse(
        status_code=202,
        body={"job_id": "j1"},
    )


async def test_check_or_store_rejects_same_key_with_different_request_hash():
    record = IdempotencyKey(
        key="job-1",
        principal_id="svc-local",
        request_hash="old-hash",
        status="completed",
        response_status_code=200,
        response_body={"ok": True},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = _FakeSession(existing=record)

    with pytest.raises(AppError) as exc_info:
        await check_or_store_idempotency_key(
            session,
            key="job-1",
            principal_id="svc-local",
            request_hash="new-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    assert exc_info.value.code == "idempotency_key_conflict"
    assert exc_info.value.status_code == 409


async def test_store_idempotency_response_marks_record_completed():
    record = IdempotencyKey(
        key="job-1",
        principal_id="svc-local",
        request_hash="hash",
        status="in_progress",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = _FakeSession(existing=record)

    await store_idempotency_response(
        session,
        key="job-1",
        principal_id="svc-local",
        status_code=201,
        response_body={"id": "created"},
    )

    assert record.status == "completed"
    assert record.response_status_code == 201
    assert record.response_body == {"id": "created"}
    assert session.flushed is True


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


def test_postgres_idempotency_store_matches_protocol():
    store = PostgresIdempotencyStore(sessionmaker=object())

    assert isinstance(store, IdempotencyStore)


def test_build_idempotency_store_requires_sessionmaker_for_postgres():
    with pytest.raises(RuntimeError, match="sessionmaker"):
        build_idempotency_store(_settings(IDEMPOTENCY_ENABLED=True))


def test_build_idempotency_store_uses_postgres_adapter():
    store = build_idempotency_store(
        _settings(IDEMPOTENCY_ENABLED=True),
        sessionmaker=object(),
    )

    assert isinstance(store, PostgresIdempotencyStore)


def test_idempotency_addon_respects_enabled_flag():
    addon = IdempotencyAddon()

    assert addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=True)) is True
    assert addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=False)) is False
