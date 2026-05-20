from typing import get_args, get_origin

from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import DbSession, get_db


def test_db_session_is_fastapi_dependency_alias():
    assert get_origin(DbSession) is not None

    session_type, dependency = get_args(DbSession)

    assert session_type is AsyncSession
    assert isinstance(dependency, Depends)
    assert dependency.dependency is get_db
