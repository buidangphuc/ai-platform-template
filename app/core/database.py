from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


def build_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.POSTGRES_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    sessionmaker = build_sessionmaker(settings)
    async with sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
