"""Smoke test for the standalone worker entry point.

Asserts the entry wires together — settings → DB → queue → store → service →
worker — without trying to actually run the polling loop. Catches import or
configuration breakage before deploys.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.bootstrap import worker as worker_module
from app.bootstrap.worker import (
    WorkerContext,
    build_worker_message_handler,
    check_worker_configuration,
    validate_worker_runtime_settings,
    worker_context,
)
from app.core.config import Settings
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import (
    AsyncPollingWorker,
    NonRetryableMessageError,
)
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.service import TaskService
from app.modules.messaging.tasks.store import TaskRecord
from scripts.run_worker import main
from tests.factories import build_test_settings


def _settings() -> Settings:
    return build_test_settings(
        # The worker stack is opt-in on the template — enable it explicitly.
        QUEUE_ENABLED=True,
        TASKS_ENABLED=True,
        QUEUE_BACKEND="memory",
        TASK_STORE_BACKEND="memory",
        WORKER_MAX_CONCURRENT=4,
    )


async def test_worker_context_wires_all_components():
    from app.modules.messaging.tasks.service import QueueTaskDispatcher

    async with worker_context(_settings()) as ctx:
        assert isinstance(ctx, WorkerContext)
        assert isinstance(ctx.worker, AsyncPollingWorker)
        assert isinstance(ctx.tasks.service, TaskService)
        assert isinstance(ctx.tasks.dispatcher, QueueTaskDispatcher)
        assert ctx.tasks.queue is ctx.tasks.dispatcher.queue
        assert ctx.tasks.store is ctx.tasks.service.store
        assert ctx.worker.max_concurrent == 4


async def test_worker_context_does_not_open_disabled_database_or_redis(monkeypatch):
    settings = _settings().model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_BACKEND": "memory",
            "TASK_STORE_BACKEND": "memory",
        }
    )

    monkeypatch.setattr(
        "app.bootstrap.resources.build_engine",
        lambda _settings: pytest.fail("database should not be opened"),
    )
    monkeypatch.setattr(
        "app.bootstrap.resources.build_redis_client",
        lambda _settings: pytest.fail("redis should not be opened"),
    )

    async with worker_context(settings) as ctx:
        assert ctx.resources.engine is None
        assert ctx.resources.redis is None


async def test_worker_context_uses_default_echo_handler():
    async with worker_context(_settings()) as ctx:
        assert isinstance(
            ctx.resources.completion_service.handler, EchoCompletionHandler
        )


async def test_worker_context_uses_the_same_handler_factory_as_the_api():
    class _CustomHandler:
        async def complete(self, request): ...

        async def stream(self, request): ...

    custom = _CustomHandler()
    seen = []

    def factory(resources, settings):
        seen.append(resources)
        return custom

    async with worker_context(_settings(), completion_handler_factory=factory) as ctx:
        assert seen == [ctx.resources]
        assert ctx.resources.completion_service.handler is custom


async def test_worker_message_handler_marks_task_completed():
    class _Service:
        def __init__(self) -> None:
            self.processing: list[str] = []
            self.completed: list[tuple[str, dict]] = []

        async def require(self, task_id: str) -> TaskRecord:
            return TaskRecord(
                id=task_id,
                type="completion",
                status=TaskStatus.QUEUED,
                payload={"messages": [{"role": "user", "content": "hello"}]},
                expires_at=datetime(2026, 5, 22, tzinfo=UTC),
            )

        async def mark_processing(self, task_id: str) -> bool:
            self.processing.append(task_id)
            return True

        async def mark_completed(self, task_id: str, result: dict) -> None:
            self.completed.append((task_id, result))

        async def mark_failed(self, task_id: str, error: str) -> None:
            pytest.fail("success path should not mark failed")

    service = _Service()
    completion_service = worker_module.CompletionService(EchoCompletionHandler())
    process_message = build_worker_message_handler(
        service=service, completion_service=completion_service
    )

    await process_message(
        QueueMessage(id="msg-1", body={"task_id": "task-1", "type": "completion"})
    )

    assert service.processing == ["task-1"]
    assert service.completed == [
        (
            "task-1",
            {"content": "echo: hello", "model": "echo", "metadata": {}},
        )
    ]


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

        async def mark_processing(self, task_id: str, **_: object) -> bool:
            return True

        async def mark_completed(self, task_id: str, result: dict) -> None:
            return None

        async def mark_failed(self, task_id: str, error: str) -> None:
            return None

        async def reclaim_stale_processing(self, **_: object) -> list:
            return []

        async def delete_expired(self, before) -> int:
            return 0

        async def close(self) -> None:
            self.closed = True

    queue = _FakeQueue()
    store = _FakeStore()

    monkeypatch.setattr(
        "app.bootstrap.resources.build_queue_gateway",
        lambda settings, backend: queue,
    )
    monkeypatch.setattr(
        "app.bootstrap.resources.build_memory_task_store",
        lambda: store,
    )

    async with worker_context(_settings()) as ctx:
        assert ctx.tasks.queue is queue
        assert ctx.tasks.store is store

    assert queue.closed is True
    assert store.closed is True


@pytest.mark.parametrize(
    "queue_backend",
    ["memory", "redis"],
)
async def test_worker_context_honors_queue_backend(queue_backend: str):
    settings = _settings().model_copy(
        update={
            "QUEUE_BACKEND": queue_backend,
            # The redis backend additionally requires the redis capability.
            "REDIS_ENABLED": queue_backend == "redis",
        }
    )
    async with worker_context(settings) as ctx:
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
        "app.bootstrap.worker.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.bootstrap.resources.build_engine",
        lambda _settings: pytest.fail("database should not be opened"),
    )

    assert check_worker_configuration() is None


def test_worker_check_cli_reports_configuration_errors(monkeypatch, capsys):
    def _raise() -> None:
        raise RuntimeError("bad worker config")

    monkeypatch.setattr("app.bootstrap.worker.check_worker_configuration", _raise)

    with pytest.raises(SystemExit) as exc_info:
        main(["--check"])

    assert exc_info.value.code == 1
    assert "worker configuration invalid: bad worker config" in capsys.readouterr().err


class _ScriptedService:
    """TaskService stand-in: records transitions, claim result is scripted."""

    def __init__(self, *, claims: bool = True) -> None:
        self.claims = claims
        self.completed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def require(self, task_id: str) -> TaskRecord:
        return TaskRecord(
            id=task_id,
            type="completion",
            status=TaskStatus.QUEUED,
            payload={"messages": [{"role": "user", "content": "hello"}]},
            expires_at=datetime(2026, 5, 22, tzinfo=UTC),
        )

    async def mark_processing(self, task_id: str) -> bool:
        return self.claims

    async def mark_completed(self, task_id: str, result: dict) -> None:
        self.completed.append(task_id)

    async def mark_failed(self, task_id: str, error: str) -> None:
        self.failed.append((task_id, error))


def _handler(service: _ScriptedService, completion_handler=None):
    return build_worker_message_handler(
        service=service,  # type: ignore[arg-type]
        completion_service=worker_module.CompletionService(
            completion_handler or EchoCompletionHandler()
        ),
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"task_id": "t-1"},
        # What the outbox used to publish: must dead-letter, not be acked.
        {"id": "e", "type": "task.completion", "payload": {"task_id": "t-1"}},
    ],
)
async def test_worker_handler_rejects_malformed_message_as_non_retryable(body):
    service = _ScriptedService()

    with pytest.raises(NonRetryableMessageError):
        await _handler(service)(QueueMessage(id="m", body=body))

    assert service.completed == [] and service.failed == []


async def test_worker_handler_skips_a_task_it_could_not_claim():
    class _Exploding:
        async def complete(self, request):
            pytest.fail("a redelivered task must not run again")

        async def stream(self, request): ...

    service = _ScriptedService(claims=False)

    await _handler(service, _Exploding())(
        QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
    )

    assert service.completed == [] and service.failed == []


async def test_worker_handler_stores_a_safe_error_and_dead_letters_failures():
    class _Leaky:
        async def complete(self, request):
            raise RuntimeError("secret upstream key sk-123 rejected")

        async def stream(self, request): ...

    service = _ScriptedService()

    with pytest.raises(NonRetryableMessageError):
        await _handler(service, _Leaky())(
            QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
        )

    [(task_id, error)] = service.failed
    assert task_id == "t-1"
    assert error.startswith("RuntimeError")
    assert "sk-123" not in error and "secret" not in error


async def test_worker_context_run_stops_the_background_loops_with_the_worker():
    import asyncio

    async with worker_context(_settings()) as ctx:
        run = asyncio.create_task(ctx.run())
        await asyncio.sleep(0.1)
        assert not run.done()

        ctx.worker.request_shutdown()
        await asyncio.wait_for(run, timeout=5)


async def test_worker_handler_runs_the_task_under_the_submitting_request_id():
    from app.core.request_context import get_request_id

    seen: list[str] = []

    class _Recording:
        async def complete(self, request):
            seen.append(get_request_id())
            return await EchoCompletionHandler().complete(request)

        async def stream(self, request): ...

    service = _ScriptedService()
    await _handler(service, _Recording())(
        QueueMessage(
            id="m",
            body={"task_id": "t-1", "type": "completion", "request_id": "req_abc"},
        )
    )

    assert seen == ["req_abc"]
    assert get_request_id() == "-"  # restored after the message
