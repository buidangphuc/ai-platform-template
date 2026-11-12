from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis

from app.modules.messaging.tasks.adapters.redis import RedisTaskStore
from app.modules.messaging.tasks.store import TaskStore

from .conformance import TaskStoreConformance, _make_task


@pytest.mark.parametrize("redis_client", [True], indirect=True)
class TestRedisTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self, redis_client: Redis, redis_prefix: str):
        async def _build() -> TaskStore:
            return RedisTaskStore(redis=redis_client, prefix=f"{redis_prefix}:tasks")

        return _build

    async def test_tasks_expire_through_a_native_ttl(
        self, redis_client: Redis, redis_prefix: str
    ):
        store = RedisTaskStore(redis=redis_client, prefix=f"{redis_prefix}:tasks")
        task = _make_task(expires_at=datetime.now(UTC) + timedelta(seconds=60))

        await store.create(task)

        ttl = await redis_client.ttl(f"{redis_prefix}:tasks:{task.id}")
        assert 50 <= ttl <= 60
        assert await store.delete_expired(before=datetime.now(UTC), limit=10) == 0
