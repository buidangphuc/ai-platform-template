import contextlib
from types import SimpleNamespace
from typing import get_args, get_origin

from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.resources import ApplicationResources
from app.core.database import DbSession, build_engine, get_db
from tests.factories import build_test_settings


def test_build_engine_applies_pool_settings():
    settings = build_test_settings(
        DB_POOL_SIZE=7,
        DB_MAX_OVERFLOW=14,
        DB_POOL_TIMEOUT_SECONDS=42,
        DB_POOL_RECYCLE_SECONDS=600,
    )

    engine = build_engine(settings)

    pool = engine.sync_engine.pool
    assert pool.size() == 7
    assert pool._max_overflow == 14
    assert pool._timeout == 42
    assert pool._recycle == 600


def test_db_session_is_fastapi_dependency_alias():
    assert get_origin(DbSession) is not None

    session_type, dependency = get_args(DbSession)

    assert session_type is AsyncSession
    assert isinstance(dependency, Depends)
    assert dependency.dependency is get_db


class _FakeSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session
        self.exited = False

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *exc_info: object) -> None:
        self.exited = True


async def test_get_db_uses_app_state_sessionmaker():
    session = object()
    context = _FakeSessionContext(session)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                resources=ApplicationResources(sessionmaker=lambda: context),
            ),
        )
    )

    dependency = get_db(request)
    yielded = await anext(dependency)
    await dependency.aclose()

    assert yielded is session
    assert context.exited is True


class _RollbackSession:
    def __init__(self) -> None:
        self.rollback_called = False

    async def rollback(self) -> None:
        self.rollback_called = True


async def test_get_db_rolls_back_on_unhandled_exception():
    session = _RollbackSession()
    context = _FakeSessionContext(session)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                resources=ApplicationResources(sessionmaker=lambda: context),
            ),
        )
    )

    dependency = get_db(request)
    yielded = await anext(dependency)

    assert yielded is session
    with contextlib.suppress(RuntimeError):
        await dependency.athrow(RuntimeError("boom"))

    assert session.rollback_called is True
    assert context.exited is True
