"""Smoke test for the standalone worker entry point.

Asserts the entry wires together — settings → DB → queue → store → service →
worker — without trying to actually run the polling loop. Catches import or
configuration breakage before deploys.
"""

from __future__ import annotations

import pytest

from app.bootstrap.worker import validate_worker_runtime_settings
from app.core.config import Settings
from app.core.worker import AsyncPollingWorker
from app.modules.tasks.service import TaskService
from app.modules.tasks.store import TaskRecord
from scripts.run_worker import (
    WorkerContext,
    _EchoCompletionHandler,
    build_worker_context,
    check_worker_configuration,
    main,
    worker_context,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        AUTH_BEARER_TOKEN="test-token",  # pragma: allowlist secret
        QUEUE_BACKEND="memory",
        TASK_STORE_BACKEND="memory",
        WORKER_MAX_CONCURRENT=4,
    )


def test_build_worker_context_wires_all_components():
    ctx = build_worker_context(_settings())

    assert isinstance(ctx, WorkerContext)
    assert isinstance(ctx.worker, AsyncPollingWorker)
    assert isinstance(ctx.service, TaskService)
    assert ctx.queue is ctx.service.queue
    assert ctx.store is ctx.service.store
    assert ctx.worker.max_concurrent == 4


def test_build_worker_context_does_not_open_unused_database_or_redis(monkeypatch):
    settings = _settings().model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_BACKEND": "memory",
            "TASK_STORE_BACKEND": "memory",
        }
    )

    monkeypatch.setattr(
        "app.bootstrap.worker.build_engine",
        lambda _settings: pytest.fail("database should not be opened"),
    )
    monkeypatch.setattr(
        "app.bootstrap.worker.build_redis_client",
        lambda _settings: pytest.fail("redis should not be opened"),
    )

    ctx = build_worker_context(settings)

    assert ctx.engine is None
    assert ctx.redis is None
    assert ctx.queue is ctx.service.queue
    assert ctx.store is ctx.service.store


def test_build_worker_context_uses_default_echo_handler():
    ctx = build_worker_context(_settings())
    assert isinstance(ctx.handler, _EchoCompletionHandler)


def test_build_worker_context_accepts_custom_handler():
    class _CustomHandler:
        async def complete(self, request): ...

        async def stream(self, request): ...

    custom = _CustomHandler()
    ctx = build_worker_context(_settings(), handler=custom)
    assert ctx.handler is custom


async def test_worker_context_manager_cleans_up_resources():
    settings = _settings()

    async with worker_context(settings) as ctx:
        assert ctx.worker is not None

    if ctx.engine is not None:
        # Engine should be disposed after context exit (subsequent dispose is a no-op).
        await ctx.engine.dispose()


async def test_worker_context_manager_closes_queue_and_store(monkeypatch):
    class _FakeQueue:
        def __init__(self) -> None:
            self.closed = False

        async def send(self, payload: dict) -> str:
            return "msg-1"

        async def receive(
            self,
            *,
            max_messages: int = 10,
            wait_seconds: float = 0.0,
        ) -> list:
            return []

        async def ack(self, message) -> None:
            return None

        async def nack(self, message, *, requeue: bool = True) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

    class _FakeStore:
        def __init__(self) -> None:
            self.closed = False

        async def create(self, task: TaskRecord) -> None:
            return None

        async def get(self, task_id: str) -> TaskRecord | None:
            return None

        async def mark_processing(self, task_id: str) -> None:
            return None

        async def mark_completed(self, task_id: str, result: dict) -> None:
            return None

        async def mark_failed(self, task_id: str, error: str) -> None:
            return None

        async def delete_expired(self, before) -> int:
            return 0

        async def close(self) -> None:
            self.closed = True

    queue = _FakeQueue()
    store = _FakeStore()

    monkeypatch.setattr(
        "app.bootstrap.worker.build_queue_gateway",
        lambda settings, *, redis=None: queue,
    )
    monkeypatch.setattr(
        "app.bootstrap.worker.build_task_store",
        lambda settings, *, sessionmaker=None, redis=None: store,
    )

    async with worker_context(_settings()) as ctx:
        assert ctx.queue is queue
        assert ctx.store is store

    assert queue.closed is True
    assert store.closed is True


@pytest.mark.parametrize(
    "queue_backend",
    ["memory", "redis"],
)
def test_build_worker_context_honors_queue_backend(queue_backend: str):
    settings = _settings().model_copy(update={"QUEUE_BACKEND": queue_backend})
    ctx = build_worker_context(settings)
    assert ctx.worker is not None


def test_worker_runtime_settings_require_queue_and_tasks_enabled():
    with pytest.raises(RuntimeError, match="QUEUE_ENABLED"):
        validate_worker_runtime_settings(
            _settings().model_copy(update={"QUEUE_ENABLED": False})
        )

    with pytest.raises(RuntimeError, match="TASKS_ENABLED"):
        validate_worker_runtime_settings(
            _settings().model_copy(update={"TASKS_ENABLED": False})
        )


def test_worker_configuration_check_validates_without_opening_sessions(monkeypatch):
    settings = _settings().model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_BACKEND": "memory",
            "TASK_STORE_BACKEND": "memory",
        }
    )

    monkeypatch.setattr(
        "scripts.run_worker.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.bootstrap.worker.build_engine",
        lambda _settings: pytest.fail("database should not be opened"),
    )

    assert check_worker_configuration() is None


def test_worker_check_cli_reports_configuration_errors(monkeypatch, capsys):
    def _raise() -> None:
        raise RuntimeError("bad worker config")

    monkeypatch.setattr("scripts.run_worker.check_worker_configuration", _raise)

    with pytest.raises(SystemExit) as exc_info:
        main(["--check"])

    assert exc_info.value.code == 1
    assert "worker configuration invalid: bad worker config" in capsys.readouterr().err
