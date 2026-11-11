import pytest
from redis.asyncio import Redis

from app.modules.messaging.tasks.adapters.redis import RedisTaskStore
from app.modules.messaging.tasks.store import TaskStore

from .conformance import TaskStoreConformance


@pytest.mark.parametrize("redis_client", [True], indirect=True)
class TestRedisTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self, redis_client: Redis, redis_prefix: str):
        async def _build() -> TaskStore:
            return RedisTaskStore(redis=redis_client, prefix=f"{redis_prefix}:tasks")

        return _build

    async def test_delete_expired_removes_only_past_tasks(self, store: TaskStore):
        pytest.skip("Redis backend uses native TTL; delete_expired is a no-op")
