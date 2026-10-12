from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.platform.quota.models import QuotaPolicy
from app.modules.platform.quota.service import QuotaService
from app.modules.platform.quota.store import QuotaStore, StaticQuotaPolicyStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.platform.mongo.gateway import MongoGateway
    from app.modules.platform.quota.adapters.mongo import MongoQuotaStore


def build_memory_quota_store() -> QuotaStore:
    from app.modules.platform.quota.adapters.memory import MemoryQuotaStore

    return MemoryQuotaStore()


def build_postgres_quota_store(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> QuotaStore:
    from app.modules.platform.quota.adapters.postgres import PostgresQuotaStore

    return PostgresQuotaStore(sessionmaker)


def build_mongo_quota_store(mongo: MongoGateway) -> MongoQuotaStore:
    from app.modules.platform.quota.adapters.mongo import MongoQuotaStore

    return MongoQuotaStore(mongo)


def build_quota_service(
    store: QuotaStore,
    *,
    policies: dict[str, QuotaPolicy] | None = None,
) -> QuotaService:
    return QuotaService(
        store=store,
        policy_store=StaticQuotaPolicyStore(policies),
    )
