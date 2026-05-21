import pytest
from fakeredis import aioredis

from app.modules.tasks.adapters.redis import RedisTaskStore
from app.modules.tasks.store import TaskStore

from .conformance import TaskStoreConformance


class TestRedisTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self):
        async def _build() -> TaskStore:
            redis = aioredis.FakeRedis(decode_responses=True)
            return RedisTaskStore(redis=redis, prefix=f"test-tasks-{id(redis)}")

        return _build

    async def test_delete_expired_removes_only_past_tasks(self, store: TaskStore):
        pytest.skip("Redis backend uses native TTL; delete_expired is a no-op")
