from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.bootstrap.state import require_app_resource
from app.core.config import Settings, get_settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.POSTGRES_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    )


def build_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def get_sessionmaker(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker

    if _sessionmaker is None:
        resolved_settings = settings or get_settings()
        _engine = build_engine(resolved_settings)
        _sessionmaker = build_sessionmaker(_engine)
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def check_postgres_connection(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        await session.execute(text("SELECT 1"))


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = require_app_resource(
        request.app,
        "sessionmaker",
        code="database_not_configured",
        message="Database session is disabled or lifespan has not opened it",
    )
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
