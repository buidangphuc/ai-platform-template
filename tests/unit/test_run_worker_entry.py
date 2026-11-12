"""Smoke test for the standalone worker entry point.

Asserts the entry wires together — settings → DB → queue → store → service →
worker — without trying to actually run the polling loop. Catches import or
configuration breakage before deploys.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.bootstrap.addons.base import default_resource_addons
from app.bootstrap.features.completions import completions_feature
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.worker import (
    WorkerContext,
    build_worker_message_handler,
    validate_worker_runtime_settings,
    worker_context,
)
from app.core.config import Settings
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import (
    AsyncPollingWorker,
    NonRetryableMessageError,
)
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.service import TaskService
from app.modules.messaging.tasks.store import TaskRecord
from scripts.run_worker import _run, main
from tests.factories import build_test_settings


def _settings() -> Settings:
    return build_test_settings(
        QUEUE_ENABLED=True,
        TASKS_ENABLED=True,
        REDIS_ENABLED=True,
        DATABASE_ENABLED=True,
        WORKER_MAX_CONCURRENT=4,
    )


async def test_worker_context_wires_all_components():
    async with worker_context(_settings()) as ctx:
        assert isinstance(ctx, WorkerContext)
        assert isinstance(ctx.worker, AsyncPollingWorker)
        assert isinstance(ctx.tasks.service, TaskService)
        assert ctx.tasks.queue is ctx.tasks.service.queue
        assert ctx.tasks.store is ctx.tasks.service.store
        assert ctx.worker.max_concurrent == 4


async def test_worker_context_does_not_open_a_disabled_database(monkeypatch):
    settings = _settings().model_copy(
        update={"DATABASE_ENABLED": False, "TASK_STORE_BACKEND": "redis"}
    )

    monkeypatch.setattr(
        "app.bootstrap.resources.build_engine",
        lambda _settings: pytest.fail("database should not be opened"),
    )

    async with worker_context(settings) as ctx:
        assert ctx.resources.engine is None
        assert ctx.resources.redis is not None


async def test_worker_context_uses_default_echo_handler():
    async with worker_context(_settings()) as ctx:
        assert isinstance(
            ctx.resources.service(CompletionService).handler, EchoCompletionHandler
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

    async with worker_context(
        _settings(), features=(completions_feature(handler_factory=factory),)
    ) as ctx:
        assert seen == [ctx.resources]
        assert ctx.resources.service(CompletionService).handler is custom


async def test_worker_message_handler_marks_task_completed():
    class _Service:
        lease_seconds = 300

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

        async def mark_completed(self, task_id: str, result: dict) -> bool:
            self.completed.append((task_id, result))
            return True

        async def mark_failed(self, task_id: str, error: str) -> bool:
            pytest.fail("success path should not mark failed")

    service = _Service()
    process_message = build_worker_message_handler(
        service=service,
        resources=_resources(EchoCompletionHandler()),
        handlers=completions_feature().tasks,
    )

    await process_message(
        QueueMessage(id="msg-1", body={"task_id": "task-1", "type": "completion"})
    )

    assert service.processing == ["task-1"]
    assert service.completed == [
        (
            "task-1",
            {
                "content": "echo: hello",
                "model": "echo",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "total_tokens": 3,
                },
                "finish_reason": "stop",
                "metadata": {},
            },
        )
    ]


async def test_worker_context_manager_closes_queue_and_store(monkeypatch):
    from app.modules.messaging.queue.adapters.redis_stream import (
        RedisStreamQueueGateway,
    )
    from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore

    closed: list[str] = []

    def spy(cls, name: str) -> None:
        original = cls.close

        async def close(self) -> None:
            closed.append(name)
            await original(self)

        monkeypatch.setattr(cls, "close", close)

    spy(RedisStreamQueueGateway, "queue")
    spy(PostgresTaskStore, "store")

    async with worker_context(_settings()) as ctx:
        assert isinstance(ctx.tasks.queue, RedisStreamQueueGateway)
        assert isinstance(ctx.tasks.store, PostgresTaskStore)
        assert closed == []

    assert sorted(closed) == ["queue", "store"]


def test_worker_runtime_settings_require_queue_and_tasks_enabled():
    with pytest.raises(RuntimeError, match="QUEUE_ENABLED"):
        validate_worker_runtime_settings(
            _settings().model_copy(update={"QUEUE_ENABLED": False})
        )

    with pytest.raises(RuntimeError, match="TASKS_ENABLED"):
        validate_worker_runtime_settings(
            _settings().model_copy(update={"TASKS_ENABLED": False})
        )


def test_check_argument_is_rejected_as_unknown(monkeypatch):
    monkeypatch.setattr(
        "scripts.run_worker._run", lambda: pytest.fail("worker must not start")
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["--check"])

    assert str(exc_info.value) == "unknown arguments: --check"


async def test_worker_context_rejects_invalid_settings_before_opening_resources(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.bootstrap.worker.open_runtime",
        lambda *args, **kwargs: pytest.fail("no resource may be opened"),
    )

    with pytest.raises(RuntimeError, match="TASKS_ENABLED"):
        async with worker_context(
            _settings().model_copy(update={"TASKS_ENABLED": False})
        ):
            pass


async def test_worker_context_opens_the_default_addons(monkeypatch):
    seen: dict = {}

    class _Stop(Exception): ...

    def fake_open_runtime(settings, **kwargs):
        seen.update(kwargs)
        raise _Stop

    monkeypatch.setattr("app.bootstrap.worker.open_runtime", fake_open_runtime)

    with pytest.raises(_Stop):
        async with worker_context(_settings()):
            pass

    assert [type(addon) for addon in seen["addons"]] == [
        type(addon) for addon in default_resource_addons()
    ]


async def test_worker_entry_logs_redacted_settings(monkeypatch):
    import contextlib

    from loguru import logger

    settings = _settings().model_copy(
        update={"REDIS_PASSWORD": "redis-secret-value"}  # pragma: allowlist secret
    )
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))

    @contextlib.asynccontextmanager
    async def fake_worker_context(_settings):
        messages.append("worker_context opened")

        class _Ctx:
            async def run(self) -> None:
                return None

        yield _Ctx()

    monkeypatch.setattr("scripts.run_worker.get_settings", lambda: settings)
    monkeypatch.setattr("scripts.run_worker.configure_logging", lambda **_: None)
    monkeypatch.setattr(
        "scripts.run_worker.worker_bootstrap.worker_context", fake_worker_context
    )
    try:
        await _run()
    finally:
        logger.remove(sink_id)

    lines = [m for m in messages if m.startswith("settings ")]
    assert len(lines) == 1
    assert "redis-secret-value" not in lines[0]
    assert messages.index(lines[0]) < messages.index("worker_context opened")


class _ScriptedService:
    """TaskService stand-in: records transitions, claim result is scripted."""

    def __init__(
        self,
        *,
        claims: bool = True,
        lease_seconds: float = 300,
        settles: bool = True,
    ) -> None:
        self.claims = claims
        self.lease_seconds = lease_seconds
        self.settles = settles
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

    async def mark_completed(self, task_id: str, result: dict) -> bool:
        self.completed.append(task_id)
        return self.settles

    async def mark_failed(self, task_id: str, error: str) -> bool:
        self.failed.append((task_id, error))
        return self.settles


def _resources(completion_handler) -> ApplicationResources:
    resources = ApplicationResources()
    resources.services[CompletionService] = CompletionService(completion_handler)
    return resources


def _handler(service: _ScriptedService, completion_handler=None):
    return build_worker_message_handler(
        service=service,  # type: ignore[arg-type]
        resources=_resources(completion_handler or EchoCompletionHandler()),
        handlers=completions_feature().tasks,
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


async def test_worker_context_run_stops_the_background_loops_with_the_worker(
    worker_settings: Settings,
):
    import asyncio

    async with worker_context(worker_settings) as ctx:
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


async def test_handler_exceeding_the_lease_is_cancelled_and_task_failed():
    import asyncio

    cancelled = asyncio.Event()

    class _Hanging:
        async def complete(self, request):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def stream(self, request): ...

    service = _ScriptedService(lease_seconds=0.05)

    with pytest.raises(NonRetryableMessageError):
        await _handler(service, _Hanging())(
            QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
        )

    assert cancelled.is_set()
    assert service.failed == [("t-1", "lease_exceeded")]
    assert service.completed == []


async def test_handler_timeout_inside_the_lease_is_an_ordinary_failure():
    class _TimingOut:
        async def complete(self, request):
            raise TimeoutError("upstream timed out")

        async def stream(self, request): ...

    service = _ScriptedService()

    with pytest.raises(NonRetryableMessageError):
        await _handler(service, _TimingOut())(
            QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
        )

    [(_, error)] = service.failed
    assert error.startswith("TimeoutError")


async def test_late_result_is_dropped_not_applied():
    from loguru import logger

    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]))
    service = _ScriptedService(settles=False)
    try:
        await _handler(service)(
            QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
        )
    finally:
        logger.remove(sink_id)

    assert service.completed == ["t-1"]
    assert any(line.startswith("worker.result_dropped task_id=t-1") for line in lines)


async def test_late_failure_is_dropped_without_dead_lettering():
    class _Failing:
        async def complete(self, request):
            raise RuntimeError("boom")

        async def stream(self, request): ...

    service = _ScriptedService(settles=False)

    await _handler(service, _Failing())(
        QueueMessage(id="m", body={"task_id": "t-1", "type": "completion"})
    )

    assert service.failed == [("t-1", "RuntimeError: task failed (see worker logs)")]
