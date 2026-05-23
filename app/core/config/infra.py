"""Infrastructure connection settings: Postgres + Redis."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class InfraSettingsMixin(BaseModel):
    DATABASE_ENABLED: bool = True
    POSTGRES_HOST: str
    POSTGRES_PORT: int = Field(default=5432, gt=0, lt=65_536)
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DB_POOL_SIZE: int = Field(default=5, gt=0)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, gt=0)

    REDIS_ENABLED: bool = True
    REDIS_HOST: str
    REDIS_PORT: int = Field(default=6379, gt=0, lt=65_536)
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = Field(default=0, ge=0)
    REDIS_TIMEOUT_SECONDS: int = Field(default=5, gt=0)

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
