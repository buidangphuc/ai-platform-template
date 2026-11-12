import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.addons.idempotency import IdempotencyAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.errors import AppError
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.factory import build_idempotency_store
from app.modules.platform.idempotency.models import IdempotencyKey
from app.modules.platform.idempotency.service import (
    build_request_hash,
    check_or_store_idempotency_key,
    compute_idempotency_expires_at,
    delete_expired_idempotency_keys,
    store_idempotency_response,
)
from app.modules.platform.idempotency.store import (
    IdempotencyCachedResponse,
    IdempotencyClaim,
)
from tests.factories import build_test_settings, open_addon

Sessions = async_sessionmaker[AsyncSession]


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def _hash(body: bytes = b"{}") -> str:
    return build_request_hash(
        method="POST", path="/jobs", body=body, principal_id="svc-local"
    )


async def _claim(
    sessions: Sessions,
    *,
    key: str = "job-1",
    request_hash: str | None = None,
    expires_at: datetime | None = None,
    timeout: int = 60,
    now: datetime | None = None,
) -> IdempotencyCachedResponse | IdempotencyClaim:
    kwargs = {} if now is None else {"now": lambda: now}
    async with sessions() as session, session.begin():
        return await check_or_store_idempotency_key(
            session,
            key=key,
            principal_id="svc-local",
            request_hash=request_hash or _hash(),
            expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
            in_progress_timeout_seconds=timeout,
            **kwargs,
        )


async def _complete(
    sessions: Sessions, claim: IdempotencyClaim, *, key: str = "job-1"
) -> bool:
    async with sessions() as session, session.begin():
        return await store_idempotency_response(
            session,
            key=key,
            principal_id="svc-local",
            claim_token=claim.token,
            status_code=202,
            response_body={"job_id": "j1"},
        )


async def _row(sessions: Sessions, key: str = "job-1") -> IdempotencyKey:
    async with sessions() as session:
        return (
            await session.scalars(
                select(IdempotencyKey).where(IdempotencyKey.key == key)
            )
        ).one()


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


def test_request_hash_includes_the_query_string():
    plain = build_request_hash(method="POST", path="/j", body=b"", principal_id="p")
    with_query = build_request_hash(
        method="POST", path="/j", body=b"", principal_id="p", query_string="a=1"
    )
    other_query = build_request_hash(
        method="POST", path="/j", body=b"", principal_id="p", query_string="a=2"
    )

    assert len({plain, with_query, other_query}) == 3


async def test_rows_written_before_body_wrapping_still_replay(
    pg_sessionmaker: Sessions,
):
    async with pg_sessionmaker() as session, session.begin():
        session.add(
            IdempotencyKey(
                key="job-1",
                principal_id="svc-local",
                request_hash=_hash(),
                status="completed",
                claim_token=None,
                response_status_code=201,
                response_body={"id": "legacy"},
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    cached = await _claim(pg_sessionmaker)

    assert cached == IdempotencyCachedResponse(status_code=201, body={"id": "legacy"})


def test_compute_idempotency_expires_at_uses_settings_ttl():
    settings = _settings(IDEMPOTENCY_TTL_SECONDS=3600)
    fixed_now = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)

    expires_at = compute_idempotency_expires_at(settings, now=lambda: fixed_now)

    assert expires_at == fixed_now + timedelta(hours=1)


async def test_check_or_store_creates_in_progress_record_for_new_key(
    pg_sessionmaker: Sessions,
):
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    claim = await _claim(pg_sessionmaker, expires_at=expires_at)

    assert isinstance(claim, IdempotencyClaim)
    assert claim.token
    row = await _row(pg_sessionmaker)
    assert row.status == "in_progress"
    assert row.claim_token == claim.token
    assert row.request_hash == _hash()
    assert row.expires_at == expires_at
    assert row.response_body is None


async def test_check_or_store_returns_cached_response_for_completed_record(
    pg_sessionmaker: Sessions,
):
    claim = await _claim(pg_sessionmaker)
    assert isinstance(claim, IdempotencyClaim)
    await _complete(pg_sessionmaker, claim)

    cached = await _claim(pg_sessionmaker)

    assert cached == IdempotencyCachedResponse(
        status_code=202,
        body={"job_id": "j1"},
    )


async def test_check_or_store_rejects_same_key_with_different_request_hash(
    pg_sessionmaker: Sessions,
):
    claim = await _claim(pg_sessionmaker, request_hash="old-hash")
    assert isinstance(claim, IdempotencyClaim)
    await _complete(pg_sessionmaker, claim)

    with pytest.raises(AppError) as exc_info:
        await _claim(pg_sessionmaker, request_hash="new-hash")

    assert exc_info.value.code == "idempotency_key_conflict"
    assert exc_info.value.status_code == 409


async def test_check_or_store_raises_in_progress_when_still_within_timeout(
    pg_sessionmaker: Sessions,
):
    await _claim(pg_sessionmaker)

    with pytest.raises(AppError) as exc_info:
        await _claim(pg_sessionmaker, timeout=60)

    assert exc_info.value.code == "idempotency_key_in_progress"


async def test_check_or_store_reclaims_stuck_in_progress_record(
    pg_sessionmaker: Sessions,
):
    stuck = await _claim(pg_sessionmaker, request_hash="old-hash")
    assert isinstance(stuck, IdempotencyClaim)
    later = datetime.now(UTC) + timedelta(minutes=5)
    new_expires = later + timedelta(hours=2)

    reclaimed = await _claim(
        pg_sessionmaker,
        request_hash="new-hash",
        expires_at=new_expires,
        timeout=60,
        now=later,
    )

    assert isinstance(reclaimed, IdempotencyClaim)
    assert reclaimed.token != stuck.token
    row = await _row(pg_sessionmaker)
    assert row.claim_token == reclaimed.token
    assert row.status == "in_progress"
    assert row.request_hash == "new-hash"
    assert row.expires_at == new_expires
    assert row.response_status_code is None
    assert row.response_body is None
    assert await _complete(pg_sessionmaker, stuck) is False
    assert await _complete(pg_sessionmaker, reclaimed) is True


async def test_check_or_store_reclaims_an_expired_completed_record(
    pg_sessionmaker: Sessions,
):
    first = await _claim(
        pg_sessionmaker, expires_at=datetime.now(UTC) + timedelta(seconds=30)
    )
    assert isinstance(first, IdempotencyClaim)
    await _complete(pg_sessionmaker, first)

    second = await _claim(pg_sessionmaker, now=datetime.now(UTC) + timedelta(hours=1))

    assert isinstance(second, IdempotencyClaim)
    assert second.token != first.token
    assert (await _row(pg_sessionmaker)).status == "in_progress"


async def test_store_idempotency_response_is_a_fenced_update(
    pg_sessionmaker: Sessions,
):
    claim = await _claim(pg_sessionmaker)
    assert isinstance(claim, IdempotencyClaim)

    async with pg_sessionmaker() as session, session.begin():
        stale = await store_idempotency_response(
            session,
            key="job-1",
            principal_id="svc-local",
            claim_token="stale-token",
            status_code=201,
            response_body={"id": "stale"},
        )
    assert stale is False
    assert (await _row(pg_sessionmaker)).status == "in_progress"

    async with pg_sessionmaker() as session, session.begin():
        stored = await store_idempotency_response(
            session,
            key="job-1",
            principal_id="svc-local",
            claim_token=claim.token,
            status_code=201,
            response_body={"id": "created"},
        )

    row = await _row(pg_sessionmaker)
    assert stored is True
    assert row.status == "completed"
    assert row.response_status_code == 201
    assert row.response_body == {"id": "created"}


async def test_conflict_path_reads_the_record_under_a_row_lock(
    pg_sessionmaker: Sessions,
):
    claim = await _claim(pg_sessionmaker)
    assert isinstance(claim, IdempotencyClaim)
    await _complete(pg_sessionmaker, claim)

    async with pg_sessionmaker() as holder, holder.begin():
        await holder.scalar(
            select(IdempotencyKey)
            .where(IdempotencyKey.key == "job-1")
            .with_for_update()
        )
        waiter = asyncio.create_task(_claim(pg_sessionmaker))
        done, _ = await asyncio.wait({waiter}, timeout=0.5)
        assert not done

    cached = await asyncio.wait_for(waiter, timeout=5)
    assert isinstance(cached, IdempotencyCachedResponse)


async def test_delete_expired_removes_only_expired_rows_up_to_the_limit(
    pg_sessionmaker: Sessions,
):
    now = datetime.now(UTC)
    for index in range(3):
        await _claim(
            pg_sessionmaker,
            key=f"old-{index}",
            expires_at=now - timedelta(hours=1),
        )
    await _claim(pg_sessionmaker, key="live", expires_at=now + timedelta(hours=1))

    async with pg_sessionmaker() as session, session.begin():
        first = await delete_expired_idempotency_keys(session, before=now, limit=2)
    async with pg_sessionmaker() as session, session.begin():
        second = await delete_expired_idempotency_keys(session, before=now, limit=500)

    assert (first, second) == (2, 1)
    async with pg_sessionmaker() as session:
        keys = list(await session.scalars(select(IdempotencyKey.key)))
    assert keys == ["live"]


async def test_delete_expired_rejects_a_non_positive_limit(
    pg_sessionmaker: Sessions,
):
    async with pg_sessionmaker() as session, session.begin():
        with pytest.raises(ValueError, match="limit must be positive"):
            await delete_expired_idempotency_keys(
                session, before=datetime.now(UTC), limit=0
            )


# ---------------------------------------------------------------- factory


def test_build_idempotency_store_uses_postgres_adapter(pg_sessionmaker: Sessions):
    store = build_idempotency_store(
        _settings(IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True),
        sessionmaker=pg_sessionmaker,
    )

    assert isinstance(store, PostgresIdempotencyStore)
    assert store.in_progress_timeout_seconds == 600


async def test_postgres_store_round_trips_a_claim_through_the_adapter(
    pg_sessionmaker: Sessions,
):
    store = build_idempotency_store(
        _settings(IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True),
        sessionmaker=pg_sessionmaker,
    )
    expired = datetime.now(UTC) - timedelta(hours=1)

    claim = await store.check_or_store(
        key="job-1", principal_id="svc-local", request_hash=_hash(), expires_at=expired
    )
    assert isinstance(claim, IdempotencyClaim)
    stored = await store.store_response(
        key="job-1",
        principal_id="svc-local",
        claim_token=claim.token,
        status_code=200,
        response_body={"ok": True},
    )
    deleted = await store.delete_expired(before=datetime.now(UTC), limit=10)
    await store.close()

    assert stored is True
    assert deleted == 1


def test_idempotency_addon_respects_enabled_flag():
    addon = IdempotencyAddon()

    assert (
        addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True))
        is True
    )
    assert addon.is_enabled(_settings(IDEMPOTENCY_ENABLED=False)) is False


async def test_idempotency_addon_attaches_a_working_store(pg_sessionmaker: Sessions):
    resources = ApplicationResources(sessionmaker=pg_sessionmaker)

    stack = await open_addon(
        IdempotencyAddon(),
        resources,
        _settings(IDEMPOTENCY_ENABLED=True, DATABASE_ENABLED=True),
    )

    assert isinstance(resources.idempotency_store, PostgresIdempotencyStore)
    claim = await resources.idempotency_store.check_or_store(
        key="job-1",
        principal_id="svc-local",
        request_hash=_hash(),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert isinstance(claim, IdempotencyClaim)
    await stack.aclose()
