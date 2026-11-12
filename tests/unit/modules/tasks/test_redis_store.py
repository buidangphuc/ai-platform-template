import asyncio
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

    async def test_concurrent_settlements_apply_once(self, store: TaskStore):
        task = _make_task()
        await store.create(task)
        await store.mark_processing(task.id, lease_seconds=60)

        outcomes = await asyncio.gather(
            *(
                store.mark_completed(task.id, {"n": n})
                if n % 2
                else store.mark_failed(task.id, f"error {n}")
                for n in range(10)
            )
        )

        assert outcomes.count(True) == 1
        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status.value in {"completed", "failed"}
