import pytest

from app.modules.tasks.adapters.memory import InMemoryTaskStore
from app.modules.tasks.store import TaskStore

from .conformance import TaskStoreConformance, _make_task


class TestInMemoryTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self):
        async def _build() -> TaskStore:
            return InMemoryTaskStore()

        return _build


async def test_in_memory_store_rejects_duplicate_id():
    store = InMemoryTaskStore()
    task = _make_task()
    await store.create(task)

    with pytest.raises(ValueError):
        await store.create(task)


async def test_in_memory_store_mark_missing_raises_key_error():
    store = InMemoryTaskStore()

    with pytest.raises(KeyError):
        await store.mark_completed("missing", {})
