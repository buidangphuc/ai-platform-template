"""End-to-end async completion: submit → worker → poll."""

import asyncio
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.worker import AsyncPollingWorker
from app.modules.queue.gateway import QueueMessage


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls.append(request)
        return CompletionResult(
            content=f"reply to: {request.messages[-1].content}",
            model="test",
            metadata={"echoed": True},
        )

    async def stream(self, request: CompletionRequest):  # pragma: no cover
        yield CompletionStreamChunk(delta="x")


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
    )


def _build_app(handler) -> FastAPI:
    return create_app(handler, settings=_settings(), init_resources=False)


async def _run_worker_for(
    app: FastAPI, handler: _RecordingHandler
) -> AsyncPollingWorker:
    service = app.state.task_service

    async def process(message: QueueMessage) -> None:
        task_id = message.body["task_id"]
        task = await service.require(task_id)
        await service.mark_processing(task_id)
        payload = CompletionRequest(**task.payload)
        result = await handler.complete(payload)
        await service.mark_completed(
            task_id,
            {
                "content": result.content,
                "model": result.model,
                "metadata": result.metadata,
            },
        )

    worker = AsyncPollingWorker(
        gateway=app.state.queue_gateway,
        handler=process,
        max_concurrent=4,
        poll_interval_seconds=0.01,
        receive_wait_seconds=0.05,
    )
    return worker


async def test_async_completion_round_trip_via_in_memory_backend():
    handler = _RecordingHandler()
    app = _build_app(handler)
    worker = await _run_worker_for(app, handler)
    worker_task = asyncio.create_task(worker.run())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        submit = await client.post(
            "/api/v1/acompletions",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer test-token"},
        )
        assert submit.status_code == 202
        task_id = submit.json()["task_id"]

        result: dict[str, Any] = {}
        for _ in range(50):
            await asyncio.sleep(0.05)
            poll = await client.get(
                f"/api/v1/acompletions/{task_id}",
                headers={"Authorization": "Bearer test-token"},
            )
            assert poll.status_code == 200
            result = poll.json()
            if result["status"] in {"completed", "failed"}:
                break

    worker.request_shutdown()
    await asyncio.wait_for(worker_task, timeout=2)

    assert result["status"] == "completed"
    assert result["result"]["content"] == "reply to: hi"
    assert result["attempts"] == 1


async def test_async_completion_returns_404_for_unknown_task():
    handler = _RecordingHandler()
    app = _build_app(handler)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/acompletions/does-not-exist",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_not_found"


async def test_async_completion_requires_auth():
    handler = _RecordingHandler()
    app = _build_app(handler)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/acompletions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 401
