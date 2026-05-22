import sys
import types

import pytest

from app.bootstrap import (
    application as application_module,
    resources as resources_module,
)
from app.bootstrap.application import _build_lifespan, create_app
from app.core.config import Settings


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


async def test_lifespan_flushes_langfuse_client_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    fake_client = _install_fake_langfuse(monkeypatch)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
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
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=False)

    async with lifespan(None):  # type: ignore[arg-type]
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

    lifespan = _build_lifespan(test_settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
        pass

    assert flush_calls == []


async def test_lifespan_flush_tolerates_missing_langfuse_package(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    monkeypatch.setitem(sys.modules, "langfuse", None)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
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
        lambda settings, *, redis=None: queue,
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_task_store",
        lambda settings, *, sessionmaker=None, redis=None: task_store,
        raising=False,
    )

    app = create_app(settings=test_settings, init_resources=True)

    assert not hasattr(app.state, "engine")
    assert not hasattr(app.state, "sessionmaker")
    assert not hasattr(app.state, "redis")
    assert not hasattr(app.state, "queue_gateway")
    assert not hasattr(app.state, "task_store")
    assert not hasattr(app.state, "task_service")

    async with app.router.lifespan_context(app):
        assert app.state.engine is engine
        assert app.state.sessionmaker is sessionmaker
        assert app.state.redis is redis
        assert app.state.queue_gateway is queue
        assert app.state.task_store is task_store
        assert app.state.task_service is not None
        assert engine.disposed is False
        assert redis.closed is False
        assert queue.closed is False
        assert task_store.closed is False

    assert engine.disposed is True
    assert redis.closed is True
    assert queue.closed is True
    assert task_store.closed is True
    assert not hasattr(app.state, "resources")
    assert not hasattr(app.state, "engine")
    assert not hasattr(app.state, "sessionmaker")
    assert not hasattr(app.state, "redis")
    assert not hasattr(app.state, "queue_gateway")
    assert not hasattr(app.state, "task_store")
    assert not hasattr(app.state, "task_service")
    assert app.state.health_service is not None


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
        lambda settings, *, redis=None: build_calls.append("queue"),
        raising=False,
    )
    monkeypatch.setattr(
        resources_module,
        "build_task_store",
        lambda settings, *, sessionmaker=None, redis=None: build_calls.append("store"),
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
        assert not hasattr(app.state, "engine")
        assert not hasattr(app.state, "sessionmaker")
        assert not hasattr(app.state, "redis")
        assert not hasattr(app.state, "queue_gateway")
        assert not hasattr(app.state, "task_store")
        assert not hasattr(app.state, "task_service")
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
        assert not hasattr(app.state, "engine")
        assert not hasattr(app.state, "redis")

    assert build_calls == []


async def test_app_lifespan_fails_fast_when_redis_queue_backend_has_no_redis(
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={
            "REDIS_ENABLED": False,
            "QUEUE_BACKEND": "redis",
        }
    )
    app = create_app(settings=settings, init_resources=True)

    with pytest.raises(
        RuntimeError, match="QUEUE_BACKEND=redis requires REDIS_ENABLED"
    ):
        async with app.router.lifespan_context(app):
            pass


async def test_app_lifespan_fails_fast_when_postgres_task_store_has_no_database(
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={
            "DATABASE_ENABLED": False,
            "TASK_STORE_BACKEND": "postgres",
        }
    )
    app = create_app(settings=settings, init_resources=True)

    with pytest.raises(
        RuntimeError,
        match="TASK_STORE_BACKEND=postgres requires DATABASE_ENABLED",
    ):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "REDIS_ENABLED": False,
                "RATE_LIMIT_BACKEND": "redis",
            },
            "Addon 'rate_limit' requires redis",
        ),
        (
            {
                "REDIS_ENABLED": False,
                "RATE_LIMIT_ENABLED": False,
                "CACHE_ENABLED": True,
                "CACHE_BACKEND": "redis",
            },
            "Addon 'cache' requires redis",
        ),
        (
            {
                "DATABASE_ENABLED": False,
                "IDEMPOTENCY_ENABLED": True,
            },
            "Addon 'idempotency' requires database",
        ),
        (
            {
                "DATABASE_ENABLED": False,
                "OUTBOX_ENABLED": True,
            },
            "Addon 'outbox' requires database",
        ),
    ],
)
async def test_app_lifespan_fails_fast_for_invalid_addon_backend_combinations(
    test_settings: Settings,
    updates: dict[str, object],
    message: str,
):
    settings = test_settings.model_copy(update=updates)
    app = create_app(settings=settings, init_resources=True)

    with pytest.raises(RuntimeError, match=message):
        async with app.router.lifespan_context(app):
            pass


async def test_object_s3_backend_fails_fast_without_bucket(test_settings: Settings):
    settings = test_settings.model_copy(
        update={
            "OBJECTS_ENABLED": True,
            "OBJECT_BACKEND": "s3",
        }
    )
    app = create_app(settings=settings, init_resources=False)

    with pytest.raises(RuntimeError, match="OBJECT_S3_BUCKET is required"):
        async with app.router.lifespan_context(app):
            pass


async def test_webhooks_fail_fast_without_signing_secret(test_settings: Settings):
    settings = test_settings.model_copy(update={"WEBHOOKS_ENABLED": True})
    app = create_app(settings=settings, init_resources=False)

    with pytest.raises(RuntimeError, match="WEBHOOK_SIGNING_SECRET is required"):
        async with app.router.lifespan_context(app):
            pass
