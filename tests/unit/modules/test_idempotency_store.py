from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.factory import (
    IdempotencyAddon,
    build_idempotency_store,
)
from app.modules.platform.idempotency.models import IdempotencyKey
from app.modules.platform.idempotency.service import (
    IdempotencyCachedResponse,
    build_request_hash,
    check_or_store_idempotency_key,
    compute_idempotency_expires_at,
    delete_expired_idempotency_keys,
    store_idempotency_response,
)
from app.modules.platform.idempotency.store import IdempotencyStore
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


class _InsertResult:
    def __init__(self, inserted_id: str | None) -> None:
        self._id = inserted_id
        self.rowcount = 1 if inserted_id else 0

    def scalar_one_or_none(self) -> str | None:
        return self._id


class _FakeSession:
    """Mocks the slice of AsyncSession used by the service layer."""

    def __init__(
        self,
        *,
        insert_inserted_id: str | None = "fake-id",
        existing: IdempotencyKey | None = None,
    ) -> None:
        self.insert_inserted_id = insert_inserted_id
        self.existing = existing
        self.flushed = False
        self.execute_calls: list[object] = []

    async def execute(self, statement):
        self.execute_calls.append(statement)
        return _InsertResult(self.insert_inserted_id)

    async def scalar(self, statement):
        return self.existing

    async def flush(self):
        self.flushed = True


def test_request_hash_scopes_key_to_method_path_body_and_principal():
    first = build_request_hash(
        method="post", path="/jobs", body=b"{}", principal_id="user-a"
    )
    same = build_request_hash(
        method="POST", path="/jobs", body=b"{}", principal_id="user-a"
    )
    other_user = build_request_hash(
        method="POST", path="/jobs", body=b"{}", principal_id="user-b"
    )

    assert first == same
    assert first != other_user


def test_compute_idempotency_expires_at_uses_settings_ttl():
    settings = _settings(IDEMPOTENCY_TTL_SECONDS=3600)
    fixed_now = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)

    expires_at = compute_idempotency_expires_at(settings, now=lambda: fixed_now)

    assert expires_at == fixed_now + timedelta(hours=1)


async def test_check_or_store_creates_in_progress_record_for_new_key():
    """When pg_insert succeeds (no conflict), service returns None."""
    session = _FakeSession(insert_inserted_id="new-id")
    request_hash = build_request_hash(
        method="POST", path="/jobs", body=b"{}", principal_id="svc-local"
    )
    expires_at = datetime(2026, 5, 22, tzinfo=UTC)

    cached = await check_or_store_idempotency_key(
        session,
        key="job-1",
        principal_id="svc-local",
        request_hash=request_hash,
        expires_at=expires_at,
        in_progress_timeout_seconds=60,
    )

    assert cached is None
    assert session.flushed is True


async def test_check_or_store_returns_cached_response_for_completed_record():
    """When pg_insert hits conflict and existing record is completed."""
    request_hash = build_request_hash(
        method="POST", path="/jobs", body=b"{}", principal_id="svc-local"
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
    session = _FakeSession(insert_inserted_id=None, existing=record)

    cached = await check_or_store_idempotency_key(
        session,
        key="job-1",
        principal_id="svc-local",
        request_hash=request_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        in_progress_timeout_seconds=60,
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
    session = _FakeSession(insert_inserted_id=None, existing=record)

    with pytest.raises(AppError) as exc_info:
        await check_or_store_idempotency_key(
            session,
            key="job-1",
            principal_id="svc-local",
            request_hash="new-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            in_progress_timeout_seconds=60,
        )

    assert exc_info.value.code == "idempotency_key_conflict"
    assert exc_info.value.status_code == 409


async def test_check_or_store_raises_in_progress_when_still_within_timeout():
    """A live in-progress record must block concurrent retries."""
    now = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)
    record = IdempotencyKey(
        key="job-1",
        principal_id="svc-local",
        request_hash="hash",
        status="in_progress",
        expires_at=now + timedelta(hours=1),
    )
    record.updated_at = now  # just updated → not stuck
    session = _FakeSession(insert_inserted_id=None, existing=record)

    with pytest.raises(AppError) as exc_info:
        await check_or_store_idempotency_key(
            session,
            key="job-1",
            principal_id="svc-local",
            request_hash="hash",
            expires_at=now + timedelta(hours=1),
            in_progress_timeout_seconds=60,
            now=lambda: now,
        )

    assert exc_info.value.code == "idempotency_key_in_progress"


async def test_check_or_store_reclaims_stuck_in_progress_record():
    """In-progress record older than timeout is treated as expired and re-claimed."""
    now = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)
    stuck = IdempotencyKey(
        key="job-1",
        principal_id="svc-local",
        request_hash="old-hash",
        status="in_progress",
        expires_at=now + timedelta(hours=1),
    )
    stuck.updated_at = now - timedelta(minutes=5)  # 300s ago, past 60s timeout
    session = _FakeSession(insert_inserted_id=None, existing=stuck)

    new_expires = now + timedelta(hours=2)
    cached = await check_or_store_idempotency_key(
        session,
        key="job-1",
        principal_id="svc-local",
        request_hash="new-hash",
        expires_at=new_expires,
        in_progress_timeout_seconds=60,
        now=lambda: now,
    )

    assert cached is None
    assert stuck.status == "in_progress"
    assert stuck.request_hash == "new-hash"
    assert stuck.expires_at == new_expires
    assert stuck.response_status_code is None
    assert stuck.response_body is None


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


async def test_delete_expired_returns_row_count():
    class _DeleteResult:
        rowcount = 3

    class _Session(_FakeSession):
        async def execute(self, statement):
            self.execute_calls.append(statement)
            return _DeleteResult()

    session = _Session()

    deleted = await delete_expired_idempotency_keys(
        session,
        before=datetime(2026, 5, 23, tzinfo=UTC),
    )

    assert deleted == 3
    assert session.flushed is True


# ---------------------------------------------------------------- factory


def test_postgres_idempotency_store_matches_protocol():
    store = PostgresIdempotencyStore(
        sessionmaker=object(),
        in_progress_timeout_seconds=60,
    )

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
    assert store.in_progress_timeout_seconds == 60


def test_idempotency_addon_respects_enabled_flag():
    addon = IdempotencyAddon()

    assert addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=True)) is True
    assert addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=False)) is False
