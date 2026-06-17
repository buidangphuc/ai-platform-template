"""Canonical completion API pattern wiring."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class RecordingCompletionHandler:
    def __init__(self) -> None:
        self.complete_requests: list[CompletionRequest] = []
        self.stream_requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.complete_requests.append(request)
        return CompletionResult(
            content=f"handled: {request.messages[-1].content}",
            model="business-model",
            metadata={"source": "handler"},
        )

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk]:
        self.stream_requests.append(request)
        yield CompletionStreamChunk(delta="hello")
        yield CompletionStreamChunk(delta=" world")


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


async def test_create_completion_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/api/v1/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 401


async def test_create_completion_requires_injected_handler(client: AsyncClient):
    response = await client.post(
        "/api/v1/completions",
        headers=await _auth_headers(client),
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "completion_handler_not_configured"


async def test_create_completion_calls_injected_handler(test_settings: Settings):
    handler = RecordingCompletionHandler()
    app = create_app(
        completion_handler=handler,
        settings=test_settings,
        init_resources=False,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/completions",
            headers=await _auth_headers(client),
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"tenant": "tenant-a"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("cmpl_")
    assert body["object"] == "completion"
    assert body["content"] == "handled: hello"
    assert body["model"] == "business-model"
    assert body["metadata"] == {"source": "handler"}
    assert handler.complete_requests[0].metadata == {"tenant": "tenant-a"}


async def test_stream_completion_calls_injected_handler(test_settings: Settings):
    handler = RecordingCompletionHandler()
    app = create_app(
        completion_handler=handler,
        settings=test_settings,
        init_resources=False,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        async with client.stream(
            "POST",
            "/api/v1/completions/stream",
            headers=await _auth_headers(client),
            json={"messages": [{"role": "user", "content": "hello"}]},
        ) as response:
            body = await response.aread()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = body.decode()
    assert 'data: {"type": "content.delta"' in text
    assert '"delta": "hello"' in text
    assert '"delta": " world"' in text
    assert 'data: {"type": "done"}' in text
    assert handler.stream_requests[0].messages[-1].content == "hello"


async def test_task_completion_submit_and_poll(test_settings: Settings):
    settings = test_settings.model_copy(
        update={
            "QUEUE_BACKEND": "memory",
            "TASK_STORE_BACKEND": "memory",
        }
    )
    app = create_app(
        completion_handler=RecordingCompletionHandler(),
        settings=settings,
        init_resources=True,
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            submit = await client.post(
                "/api/v1/completions/tasks",
                headers=await _auth_headers(client),
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
            task_id = submit.json()["task_id"]
            poll = await client.get(
                f"/api/v1/completions/tasks/{task_id}",
                headers=await _auth_headers(client),
            )

    assert submit.status_code == 202
    assert submit.json()["status"] == "queued"
    assert poll.status_code == 200
    assert poll.json()["id"] == task_id
    assert poll.json()["type"] == "completion"


async def test_task_completion_returns_503_when_tasks_disabled(
    test_settings: Settings,
):
    settings = test_settings.model_copy(update={"TASKS_ENABLED": False})
    app = create_app(
        completion_handler=RecordingCompletionHandler(),
        settings=settings,
        init_resources=True,
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/completions/tasks",
                headers=await _auth_headers(client),
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "task_service_not_configured"
