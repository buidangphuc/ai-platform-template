import sys
import types
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app.bootstrap import (
    application as application_module,
    resources as resources_module,
)
from app.bootstrap.application import _build_lifespan, create_app
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.services import (
    default_completion_guards_factory,
    default_completion_handler_factory,
)
from app.core.config import Settings
from app.core.health import HealthService


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


def _install_fake_langfuse(monkeypatch: pytest.MonkeyPatch) -> _FakeLangfuseClient:
    client = _FakeLangfuseClient()
    fake_module = types.ModuleType("langfuse")
    fake_module.get_client = lambda: client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)
    return client


def _bare_app() -> FastAPI:
    app = FastAPI()
    app.state.resources = ApplicationResources()
    app.state.in_flight_tracker = None
    app.state.health_service = HealthService(check_external_dependencies=False)
    return app


def _patch_resource_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _noop_runtime(settings, **_kwargs):
        yield ApplicationResources()

    monkeypatch.setattr(application_module, "open_runtime", _noop_runtime)


async def test_lifespan_flushes_langfuse_client_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    fake_client = _install_fake_langfuse(monkeypatch)
    _patch_resource_lifecycle(monkeypatch)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(
        settings,
        init_resources=True,
        addons=(),
        completion_handler_factory=default_completion_handler_factory,
        completion_guards_factory=default_completion_guards_factory,
    )

    async with lifespan(_bare_app()):
        assert fake_client.flushed is False

    assert fake_client.flushed is True


async def test_lifespan_skips_flush_when_init_resources_is_false(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    flush_calls: list[str] = []

    def _should_not_be_called() -> None:
        flush_calls.append("called")

    monkeypatch.setattr(
        application_module,
        "_flush_langfuse_client",
        _should_not_be_called,
    )
    _patch_resource_lifecycle(monkeypatch)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(
        settings,
        init_resources=False,
        addons=(),
        completion_handler_factory=default_completion_handler_factory,
        completion_guards_factory=default_completion_guards_factory,
    )

    async with lifespan(_bare_app()):
        pass

    assert flush_calls == []


async def test_lifespan_skips_flush_when_langfuse_disabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    flush_calls: list[str] = []

    monkeypatch.setattr(
        application_module,
        "_flush_langfuse_client",
        lambda: flush_calls.append("called"),
    )
    _patch_resource_lifecycle(monkeypatch)

    lifespan = _build_lifespan(
        test_settings,
        init_resources=True,
        addons=(),
        completion_handler_factory=default_completion_handler_factory,
        completion_guards_factory=default_completion_guards_factory,
    )

    async with lifespan(_bare_app()):
        pass

    assert flush_calls == []


async def test_lifespan_flush_tolerates_missing_langfuse_package(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    monkeypatch.setitem(sys.modules, "langfuse", None)
    _patch_resource_lifecycle(monkeypatch)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(
        settings,
        init_resources=True,
        addons=(),
        completion_handler_factory=default_completion_handler_factory,
        completion_guards_factory=default_completion_guards_factory,
    )

    async with lifespan(_bare_app()):
        pass


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeQueue:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeTaskStore:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeMongoClient:
    def __init__(self) -> None:
        self.closed = False
        self.admin = self

    def __getitem__(self, database: str) -> dict:
        return {}

    async def command(self, command: str) -> dict:
        return {"ok": 1}

    def close(self) -> None:
        self.closed = True


async def test_app_lifespan_owns_database_and_redis_resources(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    engine = _FakeEngine()
    redis = _FakeRedis()
    queue = _FakeQueue()
    task_store = _FakeTaskStore()
    sessionmaker = object()

    monkeypatch.setattr(
        resources_module,
        "build_engine",
        lambda settings: engine,
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_sessionmaker",
        lambda received_engine: sessionmaker,
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_redis_client",
        lambda settings: redis,
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_queue_gateway",
        lambda settings, backend: queue,
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_memory_task_store",
        lambda: task_store,
        raising=False,
    )

    stack_settings = test_settings.model_copy(
        update={
            # This test exercises the opt-in infra stack — enable it.
            "DATABASE_ENABLED": True,
            "REDIS_ENABLED": True,
            "QUEUE_ENABLED": True,
            "TASKS_ENABLED": True,
        }
    )
    app = create_app(settings=stack_settings, init_resources=True)
    resources_before = app.state.resources

    assert resources_before.engine is None
    assert resources_before.sessionmaker is None
    assert resources_before.redis is None
    assert resources_before.queue_gateway is None
    assert resources_before.tasks is None

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is engine
        assert resources_open.sessionmaker is sessionmaker
        assert resources_open.redis is redis
        assert resources_open.queue_gateway is queue
        assert resources_open.tasks is not None
        assert resources_open.tasks.store is task_store
        assert engine.disposed is False
        assert redis.closed is False
        assert queue.closed is False
        assert task_store.closed is False

    resources_closed = app.state.resources
    assert engine.disposed is True
    assert redis.closed is True
    assert queue.closed is True
    assert task_store.closed is True
    assert resources_closed.engine is None
    assert resources_closed.redis is None
    assert resources_closed.queue_gateway is None
    assert resources_closed.tasks is None
    assert app.state.health_service is not None


async def test_app_lifespan_owns_mongo_addon_resource(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    mongo_client = _FakeMongoClient()
    settings = test_settings.model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_ENABLED": False,
            "TASKS_ENABLED": False,
            "MONGO_ENABLED": True,
        }
    )
    monkeypatch.setattr(
        "app.modules.platform.mongo.factory.build_mongo_client",
        lambda received_settings: mongo_client,
    )

    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.mongo is not None
        readiness = await app.state.health_service.readiness()
        assert readiness.dependencies["mongo"] == "ok"
        assert mongo_client.closed is False

    assert app.state.resources.mongo is None
    assert mongo_client.closed is True


async def test_app_lifespan_honors_resource_flags(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    build_calls: list[str] = []

    monkeypatch.setattr(
        resources_module,
        "build_engine",
        lambda settings: build_calls.append("engine"),
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_redis_client",
        lambda settings: build_calls.append("redis"),
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_queue_gateway",
        lambda settings, backend: build_calls.append("queue"),
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_memory_task_store",
        lambda: build_calls.append("store"),
        raising=False,
    )
    settings = test_settings.model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_ENABLED": False,
            "TASKS_ENABLED": False,
        }
    )
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is None
        assert resources_open.sessionmaker is None
        assert resources_open.redis is None
        assert resources_open.queue_gateway is None
        assert resources_open.tasks is None
        assert app.state.health_service is not None

    assert build_calls == []


async def test_app_lifespan_init_resources_false_opens_no_runtime_resources(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    build_calls: list[str] = []

    monkeypatch.setattr(
        resources_module,
        "build_engine",
        lambda settings: build_calls.append("engine"),
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_redis_client",
        lambda settings: build_calls.append("redis"),
        raising=False,
    )
    app = create_app(settings=test_settings, init_resources=False)

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is None
        assert resources_open.redis is None

    assert build_calls == []


def test_resource_lifecycle_uses_named_open_steps():
    for name in (
        "_open_database",
        "_open_redis",
        "_open_queue",
        "_open_tasks",
        "build_health_service",
    ):
        assert callable(getattr(resources_module, name))
