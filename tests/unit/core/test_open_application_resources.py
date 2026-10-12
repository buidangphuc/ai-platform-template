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
        TASK_STORE_BACKEND="memory",
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

    async def open(self, resources: ApplicationResources, settings: Settings) -> None:
        if self.fail_on_open:
            raise RuntimeError(f"{self.name} failed")
        self.log.append(f"open:{self.name}")

    async def close(self, resources: ApplicationResources) -> None:
        self.log.append(f"close:{self.name}")


async def test_outbox_store_is_built_once_and_shared_with_dispatcher():
    from app.bootstrap.addons.base import default_resource_addons

    async with open_application_resources(
        _outbox_settings(),
        init_resources=True,
        addons=default_resource_addons(),
    ) as resources:
        assert resources.tasks is not None
        assert resources.outbox_store is not None
        assert resources.tasks.dispatcher.outbox is resources.outbox_store


async def test_worker_opens_outbox_dispatch_with_non_postgres_task_store():
    async with worker_context(_outbox_settings()) as ctx:
        assert ctx.tasks.dispatcher.outbox is ctx.resources.outbox_store


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
