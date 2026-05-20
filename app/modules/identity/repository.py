from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._memory: dict[str, ApiKey] = {}

    async def create(self, *, name: str, key_hash: str) -> ApiKey:
        api_key = ApiKey(
            id=f"key_{uuid4().hex}",
            name=name,
            key_hash=key_hash,
            is_active=True,
        )
        if self.db is None:
            self._memory[api_key.id] = api_key
            return api_key
        self.db.add(api_key)
        await self.db.flush()
        return api_key

    async def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        if self.db is None:
            return next(
                (
                    item
                    for item in self._memory.values()
                    if item.key_hash == key_hash and item.is_active
                ),
                None,
            )
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)
            )
        )
        return result.scalar_one_or_none()
