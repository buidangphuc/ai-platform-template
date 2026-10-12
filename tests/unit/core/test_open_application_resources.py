from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import pytest

from app.bootstrap.resources import ApplicationResources, open_application_resources
from app.bootstrap.worker import worker_context
from app.core.config import Settings
from tests.factories import build_test_settings


def _outbox_settings() -> Settings:
    return build_test_settings(
        DATABASE_ENABLED=True,
        QUEUE_ENABLED=True,
        QUEUE_BACKEND="memory",
        TASKS_ENABLED=True,
        TASK_STORE_BACKEND="postgres",
        TASKS_DISPATCH_BACKEND="outbox",
        OUTBOX_ENABLED=True,
        OUTBOX_BACKEND="postgres",
    )


@dataclass
class _Addon:
    name: str
    log: list[str]
    fail_on_open: bool = False
    enabled: bool = True
    opened: list[str] = field(default_factory=list)

    def is_enabled(self, settings: Settings) -> bool:
        return self.enabled

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        if self.fail_on_open:
            raise RuntimeError(f"{self.name} failed")
        self.log.append(f"open:{self.name}")
        stack.callback(self.log.append, f"close:{self.name}")


async def test_outbox_dispatch_writes_task_and_event_on_the_shared_sessionmaker():
    from app.bootstrap.addons.base import default_resource_addons
    from app.modules.messaging.tasks.outbox import PostgresTaskOutboxDispatcher

    async with open_application_resources(
        _outbox_settings(),
        init_resources=True,
        addons=default_resource_addons(),
    ) as resources:
        assert resources.tasks is not None
        assert resources.outbox_store is not None
        dispatcher = resources.tasks.dispatcher
        assert isinstance(dispatcher, PostgresTaskOutboxDispatcher)
        assert dispatcher.sessionmaker is resources.sessionmaker


async def test_worker_owns_the_outbox_relay_reclaim_and_cleanup_loops():
    async with worker_context(_outbox_settings()) as ctx:
        assert len(ctx.loops) == 3


async def test_worker_with_queue_dispatch_runs_reclaim_and_cleanup_only():
    settings = _outbox_settings().model_copy(update={"TASKS_DISPATCH_BACKEND": "queue"})
    async with worker_context(settings) as ctx:
        assert len(ctx.loops) == 2


async def test_addons_close_in_reverse_order():
    log: list[str] = []
    addons = (_Addon("a", log), _Addon("b", log))

    async with open_application_resources(
        build_test_settings(), init_resources=False, addons=addons
    ):
        assert log == ["open:a", "open:b"]

    assert log == ["open:a", "open:b", "close:b", "close:a"]


async def test_failed_open_closes_what_was_already_opened():
    log: list[str] = []
    addons = (_Addon("a", log), _Addon("b", log, fail_on_open=True))

    with pytest.raises(RuntimeError, match="b failed"):
        async with open_application_resources(
            build_test_settings(), init_resources=False, addons=addons
        ):
            pass

    assert log == ["open:a", "close:a"]
