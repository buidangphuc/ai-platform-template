import json

from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.bootstrap.application import create_app
from app.bootstrap.worker import worker_context
from app.core.config import Settings
from tests.factories import build_test_settings

HEADERS = {"Authorization": "Bearer test-token"}
BODY = {"messages": [{"role": "user", "content": "hello"}]}


async def _client(app):
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


async def test_sync_completion_uses_the_fake_model_when_llm_enabled():
    app = create_app(
        settings=build_test_settings(LLM_ENABLED=True), init_resources=False
    )

    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            response = await client.post(
                "/api/v1/completions", headers=HEADERS, json=BODY
            )

    assert response.status_code == 200
    content = response.json()["content"]
    assert content == "fake response"
    assert not content.startswith("echo:")


async def test_stream_completion_uses_the_fake_model_when_llm_enabled():
    app = create_app(
        settings=build_test_settings(LLM_ENABLED=True), init_resources=False
    )

    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            response = await client.post(
                "/api/v1/completions/stream", headers=HEADERS, json=BODY
            )

    assert response.status_code == 200
    text = response.text
    assert "content.delta" in text
    assert "echo:" not in text
    deltas = [
        line
        for line in text.splitlines()
        if line.startswith("data:") and "delta" in line
    ]
    assert "".join(json.loads(line[5:])["delta"] for line in deltas) == "fake response"


async def test_default_settings_still_echo():
    app = create_app(settings=build_test_settings(), init_resources=False)

    async with app.router.lifespan_context(app):
        assert app.state.resources.llm is None
        async with await _client(app) as client:
            response = await client.post(
                "/api/v1/completions", headers=HEADERS, json=BODY
            )

    assert response.json()["content"] == "echo: hello"


async def test_worker_task_uses_the_same_llm_handler(worker_settings: Settings):
    settings = worker_settings.model_copy(update={"LLM_ENABLED": True})

    async with worker_context(settings) as ctx:
        assert ctx.resources.llm is not None
        task = await ctx.tasks.service.submit(
            type="completion", payload=BODY, principal_id="alice"
        )
        [message] = await ctx.tasks.queue.receive(max_messages=1)
        await ctx.worker.handler(message)
        done = await ctx.tasks.service.require(task.id)

    assert done.result is not None
    assert done.result["content"] == "fake response"


async def test_worker_completion_is_observed_once(worker_settings: Settings):
    lines: list[str] = []
    settings = worker_settings.model_copy(update={"LLM_ENABLED": True})

    async with worker_context(settings) as ctx:
        sink = logger.add(lines.append, format="{message}")
        try:
            await ctx.tasks.service.submit(
                type="completion", payload=BODY, principal_id="alice"
            )
            [message] = await ctx.tasks.queue.receive(max_messages=1)
            await ctx.worker.handler(message)
        finally:
            logger.remove(sink)

    [line] = [ln for ln in lines if ln.startswith("completion ")]
    assert "mode=sync outcome=ok" in line
