"""Infrastructure connection settings: Postgres + Redis."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field
from sqlalchemy.engine import URL


class InfraSettingsMixin(BaseModel):
    DATABASE_ENABLED: bool = False
    POSTGRES_HOST: str
    POSTGRES_PORT: int = Field(default=5432, gt=0, lt=65_536)
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DB_POOL_SIZE: int = Field(default=5, gt=0)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, gt=0)

    REDIS_ENABLED: bool = False
    REDIS_HOST: str
    REDIS_PORT: int = Field(default=6379, gt=0, lt=65_536)
    REDIS_USERNAME: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = Field(default=0, ge=0)
    REDIS_TIMEOUT_SECONDS: int = Field(default=5, gt=0)

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)
