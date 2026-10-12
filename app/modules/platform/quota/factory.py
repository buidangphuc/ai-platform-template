from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.platform.quota.models import QuotaPolicy
from app.modules.platform.quota.service import QuotaService
from app.modules.platform.quota.store import StaticQuotaPolicyStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.platform.mongo.gateway import MongoGateway


def build_quota_service(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    mongo: MongoGateway | None = None,
    policies: dict[str, QuotaPolicy] | None = None,
) -> QuotaService:
    if settings.QUOTA_BACKEND == "memory":
        from app.modules.platform.quota.adapters.memory import MemoryQuotaStore

        store = MemoryQuotaStore()
    elif settings.QUOTA_BACKEND == "postgres":
        if sessionmaker is None:
            raise RuntimeError("sessionmaker is required for postgres quota backend")
        from app.modules.platform.quota.adapters.postgres import PostgresQuotaStore

        store = PostgresQuotaStore(sessionmaker)
    elif settings.QUOTA_BACKEND == "mongo":
        if mongo is None:
            raise RuntimeError("mongo gateway is required for mongo quota backend")
        from app.modules.platform.quota.adapters.mongo import MongoQuotaStore

        store = MongoQuotaStore(mongo)
    else:
        raise ValueError(f"Unknown QUOTA_BACKEND={settings.QUOTA_BACKEND!r}")

    return QuotaService(
        store=store,
        policy_store=StaticQuotaPolicyStore(policies),
    )
